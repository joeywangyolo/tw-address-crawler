"""
戶政門牌資料爬蟲

這個爬蟲的設計考量:
1. 支援 token 重複使用機制，只需要一次驗證碼就可以查詢多個行政區
2. OCR 自動識別驗證碼，失敗時會自動重試，超過上限才改手動輸入
3. 批量查詢所有行政區並輸出 CSV 檔案
"""
import requests
import re
import time
import json
import os
import csv
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime

# ============================================================
# 載入資料庫模組
# 如果沒有安裝 pymysql 或資料庫不可用，會自動跳過資料庫存儲
# ============================================================
try:
    from database.db_manager import DatabaseManager, DBConfig
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

try:
    from utils.notifier import notifier
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

GREEN = '\033[92m'
YELLOW = '\033[93m'
RED = '\033[91m'
BLUE = '\033[94m'
MAGENTA = '\033[95m'
CYAN = '\033[96m'
RESET = '\033[0m'

# ============================================================
# Pillow 12.x 相容性修正
# ddddocr 依賴舊版 Pillow 的 ANTIALIAS 屬性，新版已改名為 LANCZOS
# 這段 patch 必須在 import ddddocr 之前執行
# ============================================================
from PIL import Image
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

# ============================================================
# 載入 ddddocr OCR 套件
# 如果沒安裝的話就標記為不可用，之後會改用手動輸入
# ============================================================
try:
    import ddddocr
    DDDDOCR_AVAILABLE = True
except ImportError:
    DDDDOCR_AVAILABLE = False
    logger.warning("ddddocr 未安裝，將使用手動輸入驗證碼")


# ============================================================
# 資料結構定義
# ============================================================
@dataclass
class QueryResult:
    """單次查詢的結果"""
    success: bool
    data: List[Dict] = field(default_factory=list)
    total_count: int = 0
    page: int = 1
    total_pages: int = 1
    error_message: str = ""
    token: str = ""  # 用於後續查詢的 token
    new_captcha_key: str = ""


@dataclass
class BatchQueryResult:
    """批量查詢的結果，包含所有行政區的資料"""
    success: bool
    all_data: List[Dict] = field(default_factory=list)
    district_results: Dict[str, int] = field(default_factory=dict)  # 各區查詢結果數量
    total_count: int = 0
    error_message: str = ""


# ============================================================
# 主要爬蟲類別
# ============================================================

class HouseholdCrawler:
    BASE_URL = "https://www.ris.gov.tw"
    
    # OCR 重試上限，超過這個次數就改手動輸入
    MAX_OCR_RETRY = 10
    
    # 城市代碼對照表
    CITIES = {
        "台北市": "63000000",
        "新北市": "65000000",
    }
    
    # 台北市各行政區代碼對照表
    TAIPEI_DISTRICTS = {
        "松山區": "63000010",
        "信義區": "63000020",
        "大安區": "63000030",
        "中山區": "63000040",
        "中正區": "63000050",
        "大同區": "63000060",
        "萬華區": "63000070",
        "文山區": "63000080", 
        "南港區": "63000090",
        "內湖區": "63000100",
        "士林區": "63000110",
        "北投區": "63000120",
    }
    
    def __init__(self, use_ocr: bool = True):
        """
        初始化爬蟲各項參數
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        })
        self.csrf_token = ""
        self.captcha_key = ""
        self.city_code = ""
        self.current_token = ""  # 用來連續查詢的 token
        
        # OCR 初始化
        self.use_ocr = use_ocr and DDDDOCR_AVAILABLE
        self.ocr = None
        if self.use_ocr:
            try:
                self.ocr = ddddocr.DdddOcr()
                logger.info("ddddocr OCR 引擎已啟用")
            except Exception as e:
                logger.error(f"OCR 初始化失敗: {e}")
                self.use_ocr = False
    
    # ============================================================
    # 第一層到第三層 API: 初始化 Session
    # 這三層是為了建立有效的 session 和取得 csrf token
    # ============================================================
    def init_session(self, city_code: str = "63000000") -> bool:
        """
        初始化 session，這個過程會打三層 API 來建立有效的 session
        
        參數:
            city_code: 城市代碼，預設為台北市 (63000000)
        
        回傳:
            True 表示初始化成功，False 表示失敗
        """
        try:
            # --------------------------------------------------
            # 第一層 API: 取得主頁面和初始 CSRF token
            # --------------------------------------------------

            logger.info("第一層 API: 取得主頁面...")
            resp = self.session.get(
                f"{self.BASE_URL}/info-doorplate/app/doorplate/main", 
                timeout=15
            )
            self.csrf_token = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text).group(1)
            logger.info(f"第一層 CSRF: {self.csrf_token[:30]}...")
            
            # --------------------------------------------------
            # 第二層 API: 選擇查詢方式 (以編釘日期查詢)
            # --------------------------------------------------

            logger.info("第二層 API: 選擇查詢方式...")
            resp = self.session.post(
                f"{self.BASE_URL}/info-doorplate/app/doorplate/map",
                data={"_csrf": self.csrf_token, "searchType": "date"},
                timeout=15
            )
            self.csrf_token = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text).group(1)
            logger.info(f"第二層 CSRF: {self.csrf_token[:30]}...")
            
            # --------------------------------------------------
            # 第三層 API: 選擇城市
            # --------------------------------------------------
            logger.info("第三層 API: 選擇城市...")
            resp = self.session.post(
                f"{self.BASE_URL}/info-doorplate/app/doorplate/query",
                data={"_csrf": self.csrf_token, "searchType": "date", "cityCode": city_code},
                timeout=15
            )
            self.csrf_token = re.search(r'name="_csrf"\s+value="([^"]+)"', resp.text).group(1)
            self.captcha_key = re.search(r'id="captchaKey_captchaKey"\s+value="([^"]+)"', resp.text).group(1)
            self.city_code = city_code
            logger.info(f"第三層 CSRF: {self.csrf_token[:30]}...")
            logger.info(f"取得 Captcha Key: {self.captcha_key}")
            
            return True
            
        except Exception as e:
            logger.error(f"初始化失敗: {e}")
            return False
    
    # ============================================================
    # 第四層 API: 取得驗證碼圖片
    # ============================================================
    def get_captcha(self, save_path: str = "captcha.png") -> Optional[bytes]:
        """
        第四層 API: 取得驗證碼圖片
        
        參數:
            save_path: 驗證碼圖片儲存路徑
        
        回傳:
            圖片的 bytes 資料，失敗時回傳 None
        """
        try:
            ts = int(time.time() * 1000)
            url = f"{self.BASE_URL}/info-doorplate/captcha/image?CAPTCHA_KEY={self.captcha_key}&time={ts}"
            logger.info("第四層 API: 取得驗證碼圖片...")
            resp = self.session.get(url, timeout=15)
            
            if resp.status_code == 200 and len(resp.content) > 100:
                with open(save_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"驗證碼圖片已儲存: {save_path}")
                return resp.content
            return None
        except Exception as e:
            logger.error(f"取得驗證碼失敗: {e}")
            return None
    
    # ============================================================
    # OCR 識別驗證碼
    # ============================================================
    def recognize_captcha_from_bytes(self, img_bytes: bytes) -> Optional[str]:
        """
        使用 OCR 識別驗證碼圖片
        
        參數:
            img_bytes: 圖片的 bytes 資料
        
        回傳:
            識別結果字串，失敗時回傳 None
        """
        if not self.use_ocr or not self.ocr:
            return None
        
        try:
            result = self.ocr.classification(img_bytes)
            
            # 驗證結果格式，這個網站的驗證碼固定是 5 個字元
            if len(result) == 5:
                return result.lower()  # 轉小寫，網站不區分大小寫
            else:
                logger.warning(f"OCR 識別結果長度異常: {len(result)} 字元，預期 5 字元")
                return None
                
        except Exception as e:
            logger.error(f"OCR 識別失敗: {e}")
            return None
    
    # ============================================================
    # OCR 重試機制
    # 會重複取得新驗證碼並嘗試識別，直到成功或達到重試上限
    # ============================================================
    def get_valid_captcha_with_retry(self, max_retry: int = None) -> Tuple[Optional[str], bool]:
        """
        使用 OCR 重試機制取得有效的驗證碼
        
        這個方法會:
        1. 取得驗證碼圖片
        2. 用 OCR 識別
        3. 如果識別失敗或格式不對，重新取得新的驗證碼再試
        4. 超過重試上限就放棄，改用手動輸入
        
        參數:
            max_retry: 最大重試次數，預設使用 MAX_OCR_RETRY
        
        回傳:
            (驗證碼字串, 是否為 OCR 識別)
            如果 OCR 全部失敗，回傳 (手動輸入的驗證碼, False)
        """
        if max_retry is None:
            max_retry = self.MAX_OCR_RETRY
        
        if not self.use_ocr:
            # OCR 不可用，直接手動輸入
            return self._manual_captcha_input(), False
        
        # 開始 OCR 重試迴圈
        for attempt in range(1, max_retry + 1):
            logger.info(f"OCR 嘗試第 {attempt}/{max_retry} 次...")
            
            # 取得驗證碼圖片
            img_bytes = self.get_captcha("captcha.png")
            if not img_bytes:
                logger.warning("取得驗證碼圖片失敗，重試中...")
                time.sleep(0.5)
                continue
            
            # OCR 識別
            captcha_result = self.recognize_captcha_from_bytes(img_bytes)
            if captcha_result:
                logger.info(f"OCR 識別成功: {captcha_result}")
                return captcha_result, True
            
            logger.warning(f"OCR 識別失敗，準備重試...")
            time.sleep(0.3)
        
        # OCR 全部失敗，記錄 log 並改用手動輸入
        logger.warning(f"OCR 連續 {max_retry} 次識別失敗，改用手動輸入")
        return self._manual_captcha_input(), False
    
    def _manual_captcha_input(self) -> str:
        """手動輸入驗證碼"""
        # 先確保有最新的驗證碼圖片
        self.get_captcha("captcha.png")
        
        # 嘗試開啟圖片讓使用者看
        try:
            os.startfile("captcha.png")
        except:
            logger.info("請手動開啟 captcha.png 查看驗證碼")
        
        print("\n" + "-" * 60)
        captcha_input = input("請輸入驗證碼: ").strip()
        return captcha_input
    
    # ============================================================
    # 第五層 API: 查詢門牌資料
    # 這是核心的查詢 API，支援使用 token 進行連續查詢
    # ============================================================
    def query(
        self, 
        area_code: str, 
        start_date: str, 
        end_date: str, 
        captcha_input: str = "",
        token: str = "",
        register_kind: str = "1", 
        page: int = 1
    ) -> QueryResult:
        """
        第五層 API: 查詢門牌資料
        
        參數:
            area_code: 行政區代碼
            start_date: 起始日期 (格式: 114-09-01)
            end_date: 結束日期 (格式: 114-11-30)
            captcha_input: 驗證碼，第一次查詢時需要
            token: 連續查詢時使用的 token，有 token 就不需要驗證碼
            register_kind: 編釘類別，1 表示門牌初編
            page: 頁碼
        
        回傳:
            QueryResult 物件，包含查詢結果
        """
        try:
            nd = int(time.time() * 1000)
            
            post_data = {
                "searchType": "date",
                "cityCode": self.city_code,
                "tkt": "-1",
                "areaCode": area_code,
                "village": "",
                "neighbor": "",
                "sDate": start_date,
                "eDate": end_date,
                "_includeNoDate": "on",
                "registerKind": register_kind,
                "captchaInput": captcha_input,
                "captchaKey": self.captcha_key,
                "_csrf": self.csrf_token,
                "floor": "",
                "lane": "",
                "alley": "",
                "number": "",
                "number1": "",
                "ext": "",
                "_search": "false",
                "nd": str(nd),
                "rows": "50",
                "page": str(page),
                "sidx": "",
                "sord": "asc",
            }
            
            # 如果有 token，加入到 post_data 中
            # 有 token 的話就不需要驗證碼了
            if token:
                post_data["token"] = token
                post_data["captchaInput"] = ""  # 清空驗證碼
            
            headers = {
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRF-TOKEN": self.csrf_token,
                "Referer": f"{self.BASE_URL}/info-doorplate/app/doorplate/query",
            }
            
            logger.info(f"第五層 API: 查詢 {area_code}...")
            resp = self.session.post(
                f"{self.BASE_URL}/info-doorplate/app/doorplate/inquiry/date",
                data=post_data,
                headers=headers,
                timeout=30
            )
            
            result = resp.json()
            
            # 從 errorMsg 中提取 token 和新的 captcha key
            # 不管查詢成功或失敗，errorMsg 裡面都會有這些資訊
            response_token = ""
            new_captcha_key = ""
            error_info = {}
            
            if result.get("errorMsg"):
                try:
                    error_info = json.loads(result["errorMsg"])
                    response_token = error_info.get("token", "")
                    new_captcha_key = error_info.get("captcha", "")
                    
                    # 更新 captcha key
                    if new_captcha_key:
                        self.captcha_key = new_captcha_key
                except Exception as e:
                    logger.warning(f"解析 errorMsg 失敗: {e}, errorMsg: {result.get('errorMsg')[:100]}...")
            else:
                logger.warning(f"API 回應沒有 errorMsg，records={result.get('records', 0)}")
            
            # 檢查是否有資料
            records = result.get("records", 0)
            rows_data = result.get("rows", [])
            
            if records > 0 or rows_data:
                # 成功取得資料
                data = [
                    {
                        "address": r.get("v1", ""), 
                        "date": r.get("v2", ""), 
                        "type": r.get("v3", "")
                    } 
                    for r in rows_data
                ]
                return QueryResult(
                    success=True,
                    data=data,
                    total_count=records,
                    page=page,
                    total_pages=result.get("total", 1),
                    token=response_token,
                    new_captcha_key=new_captcha_key
                )
            
            # 檢查是否有錯誤
            if error_info.get("error"):
                return QueryResult(
                    success=False,
                    error_message=error_info.get("title", "查詢失敗"),
                    token=response_token,
                    new_captcha_key=new_captcha_key
                )
            
            # 查無資料但沒有錯誤
            if error_info.get("title") == "查無資料":
                return QueryResult(
                    success=True, 
                    data=[], 
                    total_count=0,
                    token=response_token,
                    new_captcha_key=new_captcha_key
                )
            
            # 無資料也無錯誤
            return QueryResult(
                success=True, 
                data=[], 
                total_count=0,
                token=response_token,
                new_captcha_key=new_captcha_key
            )
            
        except Exception as e:
            logger.error(f"查詢失敗: {e}")
            return QueryResult(success=False, error_message=str(e))
    
    # ============================================================
    # 查詢所有分頁: 根據 total 自動爬取所有頁面
    # ============================================================
    def query_all_pages(
        self,
        area_code: str,
        start_date: str,
        end_date: str,
        captcha_input: str = "",
        register_kind: str = "1",
        token: str = ""
    ) -> QueryResult:
        """
        查詢所有分頁的資料
        
        這個方法會:
        1. 先查詢第一頁，取得 total (總頁數)
        2. 用 token 繼續查詢第 2 頁到第 N 頁
        3. 合併所有資料返回
        
        參數:
            area_code: 行政區代碼
            start_date: 起始日期
            end_date: 結束日期
            captcha_input: 驗證碼 (只有第一頁需要，有 token 時可為空)
            register_kind: 編釘類別
            token: token (有的話就不需要驗證碼)
        
        回傳:
            QueryResult 物件，包含所有頁面的資料
        """
        all_data = []
        current_token = token
        current_captcha_key = ""  # 追蹤最新的 captcha_key
        
        # 第一頁查詢
        first_result = self.query(
            area_code=area_code,
            start_date=start_date,
            end_date=end_date,
            captcha_input=captcha_input,
            register_kind=register_kind,
            token=current_token,
            page=1
        )
        
        if not first_result.success:
            return first_result
        
        # 收集第一頁資料
        all_data.extend(first_result.data)
        total_pages = first_result.total_pages or 1 # 找到總頁數 
        total_records = first_result.total_count
        current_token = first_result.token
        current_captcha_key = first_result.new_captcha_key or ""
        
        logger.info(f"第 1/{total_pages} 頁，本頁 {len(first_result.data)} 筆，總共 {total_records} 筆")
        
        # 查詢後續分頁
        if total_pages > 1:
            for page_num in range(2, total_pages + 1):
                # 用 token 查詢下一頁，不需要驗證碼
                page_result = self.query(
                    area_code=area_code,
                    start_date=start_date,
                    end_date=end_date,
                    captcha_input="",  # 分頁不需要驗證碼
                    register_kind=register_kind,
                    token=current_token,
                    page=page_num
                )
                
                if page_result.success:
                    all_data.extend(page_result.data)
                    # 更新 token 和 captcha_key 供下一頁/下一個行政區使用
                    if page_result.token:
                        current_token = page_result.token
                    if page_result.new_captcha_key:
                        current_captcha_key = page_result.new_captcha_key
                    logger.info(f"第 {page_num}/{total_pages} 頁，本頁 {len(page_result.data)} 筆")
                else:
                    logger.warning(f"第 {page_num} 頁查詢失敗: {page_result.error_message}")
                    # 分頁失敗不中斷，繼續嘗試下一頁
                
                # 分頁間隔，避免太快
                time.sleep(0.3)
        
        logger.info(f"分頁查詢完成，共 {len(all_data)} 筆資料")
        
        return QueryResult(
            success=True,
            data=all_data,
            total_count=len(all_data),
            page=total_pages,
            total_pages=total_pages,
            token=current_token,
            new_captcha_key=current_captcha_key  # 使用最後一頁的 captcha_key
        )
    

    # ============================================================
    # 批量查詢: 查詢所有行政區
    # 利用 token 機制，只需要一次驗證碼就可以查詢多個行政區
    # ============================================================
    def batch_query_all_districts(
        self,
        districts: Dict[str, str],
        start_date: str,
        end_date: str,
        register_kind: str = "1",
        db_manager: "DatabaseManager" = None,
        city_name: str = "台北市",
        batch_id: int = None,
    ) -> BatchQueryResult:
        """
        批量查詢所有行政區
        
        這個方法會:
        1. 先用驗證碼完成第一次查詢，取得 token
        2. 後續查詢都使用 token，不需要再輸入驗證碼
        
        參數:
            districts: 行政區代碼對照表，例如 TAIPEI_DISTRICTS
            start_date: 起始日期
            end_date: 結束日期
            register_kind: 編釘類別
            db_manager: 資料庫管理器
            city_name: 城市名稱
            batch_id: 批次 ID，用於關聯資料庫記錄
        
        回傳:
            BatchQueryResult 物件，包含所有行政區的查詢結果
        """
        all_data = []
        district_results = {}
        current_token = ""
        is_first_query = True
        
        district_list = list(districts.items())
        total_districts = len(district_list)
        
        logger.info(f"開始批量查詢 {total_districts} 個行政區...")
        logger.info(f"查詢條件: {start_date} ~ {end_date}, 編釘類別: {register_kind}")
        if batch_id:
            logger.info(f"批次 ID: {batch_id}")
        
        for idx, (district_name, area_code) in enumerate(district_list, 1):
            logger.info(f"[{idx}/{total_districts}] 查詢 {district_name} ({area_code})...")
            
            if is_first_query:
                # 第一次查詢需要驗證碼
                # 使用 OCR 重試機制直到成功
                success = False
                retry_count = 0
                max_total_retry = self.MAX_OCR_RETRY
                
                while not success and retry_count < max_total_retry:
                    retry_count += 1
                    
                    # 取得驗證碼 (使用預設的 MAX_OCR_RETRY 次數)
                    captcha_input, is_ocr = self.get_valid_captcha_with_retry()
                    
                    if not captcha_input:
                        logger.error("無法取得驗證碼")
                        continue
                    
                    logger.info(f"第一次查詢，使用驗證碼: {captcha_input} (OCR: {is_ocr})")
                    
                    # 使用 query_all_pages 查詢所有分頁
                    result = self.query_all_pages(
                        area_code=area_code,
                        start_date=start_date,
                        end_date=end_date,
                        captcha_input=captcha_input,
                        register_kind=register_kind
                    )
                    
                    if result.success:
                        success = True
                        current_token = result.token
                        is_first_query = False
                        
                        # 更新 captcha_key 供後續查詢使用
                        if result.new_captcha_key:
                            self.captcha_key = result.new_captcha_key

                        # 記錄結果
                        for item in result.data:
                            item["district"] = district_name
                        all_data.extend(result.data)
                        district_results[district_name] = result.total_count
                        
                        pages_info = f" ({result.total_pages} 頁)" if result.total_pages > 1 else ""
                        logger.info(f"{district_name}: 找到 {result.total_count} 筆資料{pages_info}")
                        logger.info(f"取得 token，後續查詢不需要驗證碼")
                        
                        # 存入資料庫
                        if db_manager and db_manager.is_connected() and batch_id and result.data:
                            db_manager.insert_records(batch_id, city_name, district_name, result.data)
                            db_manager.insert_district_result(
                                batch_id, city_name, area_code, district_name, 
                                result.total_count, "success" if result.total_count > 0 else "no_data"
                            )
                        
                    elif "驗證碼" in result.error_message:
                        logger.warning(f"驗證碼錯誤 ({retry_count}/{max_total_retry})，重試中...")
                    else:
                        logger.error(f"查詢失敗: {result.error_message}")
                        break
                
                if not success:
                    logger.error(f"第一次查詢失敗，無法繼續批量查詢")
                    return BatchQueryResult(
                        success=False,
                        error_message="第一次查詢失敗，無法取得 token"
                    )
            else:
                # 後續查詢使用 token，不需要驗證碼
                # 使用 query_all_pages 查詢所有分頁
                result = self.query_all_pages(
                    area_code=area_code,
                    start_date=start_date,
                    end_date=end_date,
                    token=current_token,
                    register_kind=register_kind
                )
                
                if result.success:
                    # 更新 token 和 captcha_key 為下次查詢使用
                    if result.token:
                        current_token = result.token
                        logger.debug(f"更新 token: {result.token[:30]}...")
                    else:
                        # 沒有返回新的 token，下一個區域需要重新取得驗證碼
                        logger.warning(f"{district_name} 沒有返回新的 token，下一區將重新取得驗證碼")
                        is_first_query = True  # 重置為第一次查詢模式
                    
                    if result.new_captcha_key:
                        self.captcha_key = result.new_captcha_key
                        logger.debug(f"更新 captcha_key: {result.new_captcha_key}")
                    else:
                        logger.warning(f"{district_name} 沒有返回新的 captcha_key")
                    
                    # 記錄結果
                    for item in result.data:
                        item["district"] = district_name
                    all_data.extend(result.data)
                    district_results[district_name] = result.total_count
                    
                    pages_info = f" ({result.total_pages} 頁)" if result.total_pages > 1 else ""
                    logger.info(f"{district_name}: 找到 {result.total_count} 筆資料{pages_info}")
                    
                    # 存入資料庫
                    if db_manager and db_manager.is_connected() and batch_id and result.data:
                        db_manager.insert_records(batch_id, city_name, district_name, result.data)
                        db_manager.insert_district_result(
                            batch_id, city_name, area_code, district_name,
                            result.total_count, "success" if result.total_count > 0 else "no_data" 
                        )
                else:
                    logger.error(f"{district_name} 查詢失敗: {result.error_message}")
                    district_results[district_name] = -1  # -1 表示查詢失敗
                    
                    # 記錄失敗狀態
                    if db_manager and db_manager.is_connected() and batch_id:
                        db_manager.insert_district_result(
                            batch_id, city_name, area_code, district_name,
                            0, "failed", result.error_message
                        )
            
            # 每次查詢間隔一下，避免太頻繁
            time.sleep(0.5)
        
        total_count = sum(v for v in district_results.values() if v > 0)
        
        logger.info("=" * 60)
        logger.info("批量查詢完成")
        logger.info(f"總共找到 {total_count} 筆資料")
        for name, count in district_results.items():
            status = f"{count} 筆" if count >= 0 else "失敗"
            logger.info(f"  {name}: {status}")
        
        return BatchQueryResult(
            success=True,
            all_data=all_data,
            district_results=district_results,
            total_count=total_count
        )


# ============================================================
# CSV 輸出功能
# 這個功能之後可以改成存入資料庫
# ============================================================
def export_to_csv(data: List[Dict], filename: str = None) -> str:
    """
    將查詢結果輸出成 CSV 檔案
    
    參數:
        data: 查詢結果資料列表
        filename: 輸出檔名，如果不指定會自動產生
    
    回傳:
        輸出的檔案路徑
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"doorplate_data_{timestamp}.csv"
    
    if not data:
        logger.warning("沒有資料可以輸出")
        return ""
    
    # 定義 CSV 欄位
    fieldnames = ["district", "address", "date", "type"]
    
    # 編釘類別對照表
    type_mapping = {
        "0": "資料維護",
        "1": "門牌初編",
        "2": "門牌改編",
        "3": "門牌增編",
        "4": "門牌合併",
        "5": "門牌廢止",
        "6": "行政區域調整",
        "7": "門牌整編",
        "8": "戶政事務合併",
        "F": "行政區域調整錯誤更正",
        "G": "門牌整編錯誤更正",
    }
    
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        
        # 寫入標題行
        writer.writerow({
            "district": "行政區",
            "address": "地址",
            "date": "編釘日期",
            "type": "編釘類別"
        })
        
        # 寫入資料
        for row in data:
            writer.writerow({
                "district": row.get("district", ""),
                "address": row.get("address", ""),
                "date": row.get("date", ""),
                "type": type_mapping.get(row.get("type", ""), row.get("type", ""))
            })
    
    logger.info(f"CSV 檔案已輸出: {filename}")
    return filename


# ============================================================
# 主程式: 批量查詢所有台北市行政區並輸出 CSV / MySQL
# ============================================================
def main(save_to_db: bool = True, save_to_csv: bool = True):
    """
    主程式
    
    參數:
        save_to_db: 是否存入資料庫，預設 True
        save_to_csv: 是否輸出 CSV，預設 True
    """
    print("=" * 60)
    print("戶政門牌資料爬蟲")
    print("=" * 60)
    
    # 建立爬蟲實例
    crawler = HouseholdCrawler(use_ocr=True)
    
    # 嘗試連線資料庫
    db_manager = None
    batch_id = None
    if save_to_db and DB_AVAILABLE:
        print("\n[資料庫] 嘗試連線...")
        try:
            db_manager = DatabaseManager()
            if db_manager.connect():
                print("[資料庫] 連線成功，資料將存入 MySQL")
                # 建立 log 記錄，取得 batch_id
                batch_id = db_manager.start_log("main()")
                if batch_id:
                    print(f"[資料庫] 建立批次記錄，batch_id: {batch_id}")
            else:
                print("[資料庫] 連線失敗，將只輸出 CSV")
                db_manager = None
        except Exception as e:
            print(f"[資料庫] 初始化失敗: {e}")
            db_manager = None
    elif save_to_db and not DB_AVAILABLE:
        print("\n[資料庫] pymysql 未安裝，將只輸出 CSV")
    
    # 初始化 session (這會打第一到第三層 API)
    print("\n[初始化] 建立 Session...")
    if not crawler.init_session("63000000"):  # 台北市
        print("初始化失敗")
        if db_manager:
            db_manager.close()
        return
    print("初始化完成")
    
    # 設定查詢條件
    start_date = "114-09-01"
    end_date = "114-11-30"
    register_kind = "1"  # 門牌初編
    
    print(f"\n[查詢條件]")
    print(f"  日期範圍: {start_date} ~ {end_date}")
    print(f"  編釘類別: {register_kind} (門牌初編)")
    print(f"  查詢區域: 台北市全部 {len(crawler.TAIPEI_DISTRICTS)} 個行政區")
    
    # 批量查詢所有行政區
    print("\n[開始批量查詢]")
    try:
        result = crawler.batch_query_all_districts(
            districts=crawler.TAIPEI_DISTRICTS,
            start_date=start_date,
            end_date=end_date,
            register_kind=register_kind,
            db_manager=db_manager,
            city_name="台北市",
            batch_id=batch_id
        )
        
        if result.success:
            print(f"\n[查詢完成] 總共找到 {result.total_count} 筆資料")
            
            # 輸出 CSV
            if result.all_data:
                csv_file = export_to_csv(result.all_data)
                print(f"\n[CSV 輸出] {csv_file}")
            else:
                print("\n[提示] 沒有資料，不產生 CSV")
                
                # 發送「查詢資料為空」通知
                if NOTIFIER_AVAILABLE and db_manager:
                    emails = db_manager.get_notification_emails()
                    if emails:
                        query_info = f"日期範圍: {start_date} ~ {end_date}\n查詢區域: 台北市全部行政區"
                        notifier.notify_empty_data(emails, query_info, batch_id)
                        print("[通知] 已發送「查詢資料為空」通知")
            
            # 資料庫存儲狀態
            if db_manager:
                print(f"[MySQL 存儲] 資料已存入資料庫")
        else:
            print(f"\n[查詢失敗] {result.error_message}")
            
            # 發送「爬蟲執行失敗」通知
            if NOTIFIER_AVAILABLE and db_manager:
                emails = db_manager.get_notification_emails()
                if emails:
                    notifier.notify_crawler_error(emails, result.error_message, batch_id)
                    print("[通知] 已發送「爬蟲執行失敗」通知")
        
        # 更新 log 狀態
        if db_manager and batch_id:
            status = "completed" if result.success else "failed"
            db_manager.end_log(batch_id, result.total_count, status, result.error_message)
            print(f"[資料庫] 批次記錄已更新，狀態: {status}")
            
    finally:
        # 關閉資料庫連線
        if db_manager:
            db_manager.close()
            print("\n[資料庫] 連線已關閉")


if __name__ == "__main__":
    main()
