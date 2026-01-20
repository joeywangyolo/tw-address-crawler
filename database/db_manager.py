"""
資料庫管理模組
負責處理所有與 MySQL 的互動

設計原則:
1. 獨立模組，不依賴爬蟲邏輯
2. 提供清晰的介面給爬蟲和未來的 API 使用
3. 支援連線池和自動重連
"""
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from contextlib import contextmanager

# MySQL 連線套件
try:
    import pymysql
    from pymysql.cursors import DictCursor
    PYMYSQL_AVAILABLE = True
except ImportError:
    PYMYSQL_AVAILABLE = False

logger = logging.getLogger(__name__)


# ============================================================
# 資料結構定義
# ============================================================
@dataclass
class DBConfig:
    """資料庫連線設定"""
    host: str = "localhost"
    port: int = 3306
    user: str = "root"
    password: str = "household123"
    database: str = "household_db"
    charset: str = "utf8mb4"
    
    @classmethod
    def from_env(cls) -> "DBConfig":
        """從環境變數讀取設定"""
        return cls(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "household123"),
            database=os.getenv("DB_NAME", "household_db"),
        )


# ============================================================
# 編釘類別對照表
# ============================================================
EDIT_TYPE_MAPPING = {
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


# ============================================================
# 資料庫管理類別
# ============================================================
class DatabaseManager:
    """
    資料庫管理器
    
    使用方式:
        db = DatabaseManager()
        if db.connect():
            db.insert_records(city, district, records)
            db.close()
    """
    
    def __init__(self, config: DBConfig = None):
        """
        初始化資料庫管理器
        
        參數:
            config: 資料庫連線設定，不指定則使用預設值或環境變數
        """
        if not PYMYSQL_AVAILABLE:
            raise ImportError("pymysql 未安裝，請執行: pip install pymysql")
        
        self.config = config or DBConfig.from_env()
        self.connection = None
        self._connected = False
    
    def connect(self) -> bool:
        """
        建立資料庫連線
        
        回傳:
            True 表示連線成功
        """
        try:
            self.connection = pymysql.connect(
                host=self.config.host,
                port=self.config.port,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                charset=self.config.charset,
                cursorclass=DictCursor,
                autocommit=False
            )
            self._connected = True
            logger.info(f"資料庫連線成功: {self.config.host}:{self.config.port}/{self.config.database}")
            return True
        except Exception as e:
            logger.error(f"資料庫連線失敗: {e}")
            self._connected = False
            return False
    
    def close(self):
        """關閉資料庫連線"""
        if self.connection:
            try:
                self.connection.close()
                logger.info("資料庫連線已關閉")
            except:
                pass
        self._connected = False
    
    def is_connected(self) -> bool:
        """檢查是否已連線"""
        if not self._connected or not self.connection:
            return False
        try:
            self.connection.ping(reconnect=True)
            return True
        except:
            self._connected = False
            return False
    
    @contextmanager
    def cursor(self):
        """取得資料庫游標的 context manager"""
        if not self.is_connected():
            raise ConnectionError("資料庫未連線")
        
        cursor = self.connection.cursor()
        try:
            yield cursor
            self.connection.commit()
        except Exception as e:
            self.connection.rollback()
            raise e
        finally:
            cursor.close()
    
    # ============================================================
    # 行政區查詢結果操作
    # ============================================================
    def insert_district_result(
        self,
        batch_id: int,
        city_name: str,
        district_code: str,
        district_name: str,
        record_count: int,
        status: str = "success",
        error_message: str = None
    ):
        """
        插入行政區查詢結果
        
        參數:
            batch_id: 批次 ID
            city_name: 城市名稱
            district_code: 行政區代碼
            district_name: 行政區名稱
            record_count: 查詢到的筆數
            status: 狀態 (success/failed/no_data)
            error_message: 錯誤訊息
        """
        sql = """
            INSERT INTO district_query_results
            (batch_id, city_name, district_code, district_name, record_count, status, error_message, queried_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        """
        
        try:
            with self.cursor() as cursor:
                cursor.execute(sql, (
                    batch_id, city_name, district_code, district_name, 
                    record_count, status, error_message
                ))
        except Exception as e:
            logger.error(f"插入行政區結果失敗: {e}")
    
    # ============================================================
    # 門牌資料操作
    # ============================================================
    def insert_records(
        self,
        batch_id: int,
        city: str,
        district: str,
        records: List[Dict]
    ) -> int:
        """
        批量插入門牌資料
        
        參數:
            batch_id: 批次 ID
            city: 城市名稱
            district: 行政區名稱
            records: 門牌資料列表，每筆包含 address, date, type
        
        回傳:
            插入的筆數
        """
        if not records:
            return 0
        
        sql = """
            INSERT INTO household_records
            (batch_id, city, district, full_address, edit_date, edit_type_code, edit_type_name, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        inserted = 0
        try:
            with self.cursor() as cursor:
                for record in records:
                    type_code = record.get("type", "")
                    type_name = EDIT_TYPE_MAPPING.get(type_code, type_code)
                    
                    cursor.execute(sql, (
                        batch_id,
                        city,
                        district,
                        record.get("address", ""),
                        record.get("date", ""),
                        type_code,
                        type_name,
                        json.dumps(record, ensure_ascii=False)
                    ))
                    inserted += 1
                
                logger.info(f"插入 {inserted} 筆資料到 {city} {district}")
        except Exception as e:
            logger.error(f"插入資料失敗: {e}")
        
        return inserted
    
    # ============================================================
    # 爬蟲 Log 操作
    # ============================================================
    def start_log(self, api_endpoint: str) -> Optional[int]:
        """
        開始記錄一次 API 呼叫
        
        參數:
            api_endpoint: API 端點名稱
        
        回傳:
            log_id，失敗時回傳 None
        """
        sql = """
            INSERT INTO crawler_logs (api_endpoint, start_time, status)
            VALUES (%s, NOW(), 'running')
        """
        try:
            with self.cursor() as cursor:
                cursor.execute(sql, (api_endpoint,))
                log_id = cursor.lastrowid
                logger.info(f"開始記錄: log_id={log_id}, endpoint={api_endpoint}")
                return log_id
        except Exception as e:
            logger.error(f"建立 log 失敗: {e}")
            return None
    
    def end_log(
        self,
        log_id: int,
        records_fetched: int = 0,
        status: str = "completed",
        error_message: str = None
    ):
        """
        結束一次 API 呼叫記錄
        
        參數:
            log_id: log ID
            records_fetched: 擷取的記錄數
            status: 狀態 (completed/failed)
            error_message: 錯誤訊息
        """
        sql = """
            UPDATE crawler_logs 
            SET end_time = NOW(), records_fetched = %s, status = %s, error_message = %s
            WHERE id = %s
        """
        try:
            with self.cursor() as cursor:
                cursor.execute(sql, (records_fetched, status, error_message, log_id))
                logger.info(f"結束記錄: log_id={log_id}, status={status}")
        except Exception as e:
            logger.error(f"更新 log 失敗: {e}")
    
    # ============================================================
    # 通知相關方法
    # ============================================================
    def get_notification_emails(self) -> List[str]:
        """
        取得所有啟用的通知信箱
        
        回傳:
            List[str]: Email 地址列表
        """
        sql = "SELECT email FROM email_address WHERE is_active = TRUE"
        try:
            with self.cursor() as cursor:
                cursor.execute(sql)
                results = cursor.fetchall()
                return [row["email"] for row in results]
        except Exception as e:
            logger.error(f"取得通知信箱失敗: {e}")
            return []
    
    def add_notification_email(self, email: str, name: str = None) -> bool:
        """
        新增通知信箱
        
        參數:
            email: Email 地址
            name: 收件人名稱
        """
        sql = "INSERT INTO email_address (email, name) VALUES (%s, %s) ON DUPLICATE KEY UPDATE is_active = TRUE"
        try:
            with self.cursor() as cursor:
                cursor.execute(sql, (email, name))
                logger.info(f"新增通知信箱: {email}")
                return True
        except Exception as e:
            logger.error(f"新增通知信箱失敗: {e}")
            return False
    
    # ============================================================
    # 查詢方法（給 API 使用）
    # ============================================================
    def search_records(
        self,
        city: str = None,
        district: str = None,
        edit_type: str = None,
        start_date: str = None,
        end_date: str = None,
        limit: int = 100
    ) -> List[Dict]:
        """
        搜尋門牌資料
        
        參數:
            city: 城市
            district: 行政區
            edit_type: 編釘類別代碼
            start_date: 起始日期
            end_date: 結束日期
            limit: 最大筆數
        """
        conditions = []
        params = []
        
        if city:
            conditions.append("city = %s")
            params.append(city)
        if district:
            conditions.append("district = %s")
            params.append(district)
        if edit_type:
            conditions.append("edit_type_code = %s")
            params.append(edit_type)
        if start_date:
            conditions.append("edit_date >= %s")
            params.append(start_date)
        if end_date:
            conditions.append("edit_date <= %s")
            params.append(end_date)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        params.append(limit)
        
        sql = f"""
            SELECT * FROM household_records
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT %s
        """
        
        try:
            with self.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"搜尋記錄失敗: {e}")
            return []


# ============================================================
# 便利函數
# ============================================================
def test_connection(config: DBConfig = None) -> bool:
    """測試資料庫連線"""
    db = DatabaseManager(config)
    if db.connect():
        print(f"連線成功: {db.config.host}:{db.config.port}/{db.config.database}")
        db.close()
        return True
    else:
        print("連線失敗")
        return False


if __name__ == "__main__":
    # 測試連線
    logging.basicConfig(level=logging.INFO)
    test_connection()
