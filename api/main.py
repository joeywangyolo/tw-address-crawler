"""
戶政門牌資料爬蟲 API
使用 FastAPI 框架

啟動方式:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

API 文件:
    http://localhost:8000/docs (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""
import sys
import os
import time
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# APScheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

# 排程器 logger
scheduler_logger = logging.getLogger("scheduler")
scheduler_logger.setLevel(logging.INFO)

# API logger
logger = logging.getLogger(__name__)

# 加入專案根目錄到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.schemas import (
    BatchQueryRequest,
    BatchQueryResponse,
    HealthResponse,
    ErrorResponse,
    HouseholdRecord
)
from crawler_requests import HouseholdCrawler, main as crawler_main

# 嘗試載入資料庫模組
try:
    from database.db_manager import DatabaseManager
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

# 嘗試載入通知模組
try:
    from utils.notifier import notifier
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False

# ============================================================
# 排程設定
# ============================================================

# 環境變數控制排程開關（上雲時可設為 false）
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"

# 排程模式：cron（固定時間）或 interval（間隔執行）
SCHEDULE_MODE = os.getenv("SCHEDULE_MODE", "cron")

# cron 模式設定（預設每天早上 9:00）
SCHEDULE_HOUR = os.getenv("SCHEDULE_HOUR", "9")  # 可設 "*" 表示每小時
SCHEDULE_MINUTE = os.getenv("SCHEDULE_MINUTE", "0")

# interval 模式設定（預設每 1 小時）
SCHEDULE_INTERVAL_HOURS = int(os.getenv("SCHEDULE_INTERVAL_HOURS", "1"))

# 查詢條件設定
SCHEDULE_START_DATE = os.getenv("SCHEDULE_START_DATE", "114-09-01")
SCHEDULE_END_DATE = os.getenv("SCHEDULE_END_DATE", "114-11-30")
SCHEDULE_REGISTER_KIND = os.getenv("SCHEDULE_REGISTER_KIND", "1")

# 建立排程器
scheduler = BackgroundScheduler(timezone="Asia/Taipei")


def scheduled_crawl_job():
    """
    排程執行的爬蟲任務
    直接呼叫 crawler_requests.py 的 main() 函數
    """
    scheduler_logger.info("=" * 60)
    scheduler_logger.info(f"[排程任務] 開始執行 - {datetime.now()}")
    scheduler_logger.info("=" * 60)
    
    try:
        # 直接呼叫 crawler_requests.py 的 main() 函數
        crawler_main()
        scheduler_logger.info("[排程任務] 執行完成")
    except Exception as e:
        scheduler_logger.error(f"[排程任務] 執行錯誤: {e}")


# ============================================================
# FastAPI 應用程式
# ============================================================

app = FastAPI(
    title="戶政門牌資料爬蟲 API",
    description="""
## 功能說明

此 API 提供戶政門牌資料的自動化查詢功能，支援：

- **批量查詢**：一次查詢多個行政區的門牌資料
- **資料庫存儲**：可選擇將結果存入 MySQL 資料庫

## 注意事項

- 批量查詢可能需要 20-30 秒，請耐心等待
- 驗證碼由系統自動處理 (OCR)，無需手動輸入
- 日期格式使用民國年 (例如: 114-09-01)
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS 設定
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 排程器生命週期
# ============================================================

@app.on_event("startup")
def start_scheduler():
    """FastAPI 啟動時啟動排程器"""
    if ENABLE_SCHEDULER:
        if SCHEDULE_MODE == "interval":
            # 間隔模式：每 N 小時執行一次
            scheduler.add_job(
                scheduled_crawl_job,
                IntervalTrigger(hours=SCHEDULE_INTERVAL_HOURS),
                id="interval_crawl",
                name=f"間隔爬蟲任務（每 {SCHEDULE_INTERVAL_HOURS} 小時）",
                replace_existing=True
            )
            scheduler.start()
            scheduler_logger.info(f"[排程器] 已啟動（間隔模式），每 {SCHEDULE_INTERVAL_HOURS} 小時執行一次")
        else:
            # cron 模式：固定時間執行（預設）
            # SCHEDULE_HOUR 可設為 "*" 表示每小時整點
            hour_val = None if SCHEDULE_HOUR == "*" else int(SCHEDULE_HOUR)
            minute_val = int(SCHEDULE_MINUTE)
            scheduler.add_job(
                scheduled_crawl_job,
                CronTrigger(hour=hour_val, minute=minute_val),
                id="cron_crawl",
                name="定時爬蟲任務",
                replace_existing=True
            )
            scheduler.start()
            hour_display = "每小時" if SCHEDULE_HOUR == "*" else f"{int(SCHEDULE_HOUR):02d}"
            scheduler_logger.info(f"[排程器] 已啟動（cron模式），執行時間: {hour_display}:{minute_val:02d}")
    else:
        scheduler_logger.info("[排程器] 已停用（ENABLE_SCHEDULER=false）")


@app.on_event("shutdown")
def shutdown_scheduler():
    """FastAPI 關閉時關閉排程器"""
    if scheduler.running:
        scheduler.shutdown()
        scheduler_logger.info("[排程器] 已關閉")


# ============================================================
# 健康檢查
# ============================================================

@app.get(
    "/api/v1/health",
    response_model=HealthResponse,
    tags=["系統"],
    summary="健康檢查"
)
def health_check():
    """
    檢查 API 服務和資料庫連線狀態
    """
    db_status = "unavailable"
    
    if DB_AVAILABLE:
        try:
            db = DatabaseManager()
            if db.connect():
                db_status = "connected"
                db.close()
            else:
                db_status = "connection_failed"
        except Exception as e:
            db_status = f"error: {str(e)}"
    
    return HealthResponse(
        status="healthy",
        database=db_status,
        version="1.0.0",
        timestamp=datetime.now()
    )


# ============================================================
# 批量查詢
# ============================================================

@app.post(
    "/api/v1/query/batch",
    response_model=BatchQueryResponse,
    responses={
        200: {"description": "查詢成功"},
        500: {"model": ErrorResponse, "description": "伺服器錯誤"}
    },
    tags=["查詢"],
    summary="批量查詢多個行政區"
)
def batch_query(request: BatchQueryRequest):
    """
    批量查詢指定縣市的多個行政區門牌資料
    
    - **city_code**: 縣市代碼 (預設: 63000000 台北市)
    - **start_date**: 起始日期 (民國年格式: 114-09-01)
    - **end_date**: 結束日期 (民國年格式: 114-11-30)
    - **register_kind**: 編釘類別 (1=初編, 2=改編, 3=廢止, 4=復用)
    - **districts**: 指定行政區列表，**直接移除該欄位（不傳入）**表示查詢全部 12 區
    - **save_to_db**: 是否存入資料庫
    
    注意: 此操作可能需要 20-30 秒完成
    """
    start_time = time.time()
    
    try:
        # 建立爬蟲實例
        crawler = HouseholdCrawler(use_ocr=True)
        
        # 初始化 session
        if not crawler.init_session():
            raise HTTPException(status_code=500, detail="無法初始化爬蟲 session")
        
        # 決定要查詢的行政區
        if request.districts:
            # 過濾出有效的行政區
            districts = {
                name: code 
                for name, code in crawler.TAIPEI_DISTRICTS.items() 
                if name in request.districts
            }
            if not districts:
                raise HTTPException(
                    status_code=400, 
                    detail=f"無效的行政區: {request.districts}"
                )
        else:
            districts = crawler.TAIPEI_DISTRICTS
        
        # 資料庫連線和 batch_id
        db_manager = None
        batch_id = None
        if request.save_to_db and DB_AVAILABLE:
            try:
                db_manager = DatabaseManager()
                if db_manager.connect():
                    # 建立 log 記錄，取得 batch_id
                    batch_id = db_manager.start_log("/api/v1/query/batch")
                else:
                    db_manager = None
            except:
                db_manager = None
        
        # 執行批量查詢
        result = crawler.batch_query_all_districts(
            districts=districts,
            start_date=request.start_date,
            end_date=request.end_date,
            register_kind=request.register_kind,
            city_name="台北市",
            db_manager=db_manager,
            batch_id=batch_id
        )
        
        # 發送異常通知
        if NOTIFIER_AVAILABLE and db_manager:
            emails = db_manager.get_notification_emails()
            if not emails:
                logger.warning("[通知] email_address 表無收件人，跳過發送通知")
            elif not result.success:
                # 爬蟲執行失敗
                notifier.notify_crawler_error(emails, result.error_message, batch_id)
                logger.info("[通知] 已發送「爬蟲執行失敗」通知")
            elif result.total_count == 0:
                # 查詢資料為空
                query_info = f"日期範圍: {request.start_date} ~ {request.end_date}\n查詢區域: {', '.join(districts.keys())}"
                notifier.notify_empty_data(emails, query_info, batch_id)
                logger.info("[通知] 已發送「查詢資料為空」通知")
        
        # 更新 log 狀態並關閉資料庫連線
        if db_manager and batch_id:
            status = "completed" if result.success else "failed"
            db_manager.end_log(batch_id, result.total_count, status, result.error_message)
        if db_manager:
            db_manager.close()
        
        execution_time = time.time() - start_time
        
        # 整理失敗的行政區
        failed_districts = [
            name for name, count in result.district_results.items() 
            if count == -1
        ]
        
        # 整理成功的行政區結果
        district_results = {
            name: count 
            for name, count in result.district_results.items() 
            if count >= 0
        }
        
        # 轉換資料格式
        records = [
            HouseholdRecord(
                address=item.get("address", ""),
                date=item.get("date", ""),
                type=item.get("type", ""),
                district=item.get("district", "")
            )
            for item in result.all_data
        ] if result.all_data else []
        
        return BatchQueryResponse(
            success=result.success,
            total_count=result.total_count,
            district_results=district_results,
            failed_districts=failed_districts,
            execution_time=round(execution_time, 2),
            data=records if len(records) <= 300 else None,  # 超過 1000 筆不返回詳細資料
            error_message=result.error_message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 取得支援的行政區列表
# ============================================================

@app.get(
    "/api/v1/districts",
    tags=["資訊"],
    summary="取得支援的行政區列表"
)
def get_districts():
    """
    取得目前支援查詢的所有行政區及其代碼
    """
    return {
        "city_name": "台北市",
        "city_code": "63000000",
        "districts": HouseholdCrawler.TAIPEI_DISTRICTS
    }


# ============================================================
# 排程管理 API
# ============================================================

@app.get(
    "/api/v1/scheduler/status",
    tags=["排程"],
    summary="查看排程狀態"
)
def get_scheduler_status():
    """
    查看排程器狀態和下次執行時間
    """
    jobs = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": str(job.next_run_time) if job.next_run_time else None
            })
    
    return {
        "enabled": ENABLE_SCHEDULER,
        "running": scheduler.running,
        "schedule_time": f"{SCHEDULE_HOUR}:{SCHEDULE_MINUTE.zfill(2)}",
        "jobs": jobs,
        "config": {
            "start_date": SCHEDULE_START_DATE,
            "end_date": SCHEDULE_END_DATE,
            "register_kind": SCHEDULE_REGISTER_KIND
        }
    }


# ============================================================
# 根路徑
# ============================================================

@app.get("/", tags=["系統"])
def root():
    """
    API 根路徑，顯示基本資訊
    """
    return {
        "name": "戶政門牌資料爬蟲 API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
        "scheduler": "/api/v1/scheduler/status"
    }


# ============================================================
# 啟動入口
# ============================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
