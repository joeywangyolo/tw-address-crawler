"""
資料庫操作模組
負責與 MySQL 資料庫的互動
"""
import json
from typing import List, Dict, Optional
from datetime import datetime
import mysql.connector
from mysql.connector import Error

from config.settings import DATABASE_CONFIG
from utils.logger import CrawlerLogger


class DatabaseHandler:
    """
    MySQL 資料庫處理器
    """
    
    def __init__(self, logger: CrawlerLogger):
        self.logger = logger
        self.connection = None
        self.session_id = None
    
    def connect(self) -> bool:
        """
        建立資料庫連線
        
        Returns:
            是否成功連線
        """
        try:
            self.connection = mysql.connector.connect(
                host=DATABASE_CONFIG["host"],
                port=DATABASE_CONFIG["port"],
                user=DATABASE_CONFIG["user"],
                password=DATABASE_CONFIG["password"],
                database=DATABASE_CONFIG["database"],
                charset="utf8mb4",
                collation="utf8mb4_unicode_ci"
            )
            
            if self.connection.is_connected():
                self.logger.log_info(f"已連線到 MySQL: {DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}")
                return True
            
        except Error as e:
            self.logger.log_error(e, "資料庫連線")
            return False
        
        return False
    
    def disconnect(self):
        """關閉資料庫連線"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            self.logger.log_info("資料庫連線已關閉")
    
    def start_session(self) -> str:
        """
        開始新的爬蟲工作階段
        
        Returns:
            工作階段 ID
        """
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        try:
            cursor = self.connection.cursor()
            sql = """
                INSERT INTO crawler_logs (session_id, start_time, status)
                VALUES (%s, %s, 'running')
            """
            cursor.execute(sql, (self.session_id, datetime.now()))
            self.connection.commit()
            cursor.close()
            
            self.logger.log_info(f"工作階段已開始: {self.session_id}")
            
        except Error as e:
            self.logger.log_error(e, "start_session")
        
        return self.session_id
    
    def end_session(self, stats: Dict, status: str = "completed", error_message: str = None):
        """
        結束爬蟲工作階段
        
        Args:
            stats: 統計資訊
            status: 狀態 (completed/failed/cancelled)
            error_message: 錯誤訊息（如果有）
        """
        if not self.session_id:
            return
        
        try:
            cursor = self.connection.cursor()
            sql = """
                UPDATE crawler_logs 
                SET end_time = %s,
                    total_requests = %s,
                    successful_requests = %s,
                    failed_requests = %s,
                    records_fetched = %s,
                    status = %s,
                    error_message = %s
                WHERE session_id = %s
            """
            cursor.execute(sql, (
                datetime.now(),
                stats.get("total_requests", 0),
                stats.get("successful_requests", 0),
                stats.get("failed_requests", 0),
                stats.get("records_fetched", 0),
                status,
                error_message,
                self.session_id
            ))
            self.connection.commit()
            cursor.close()
            
            self.logger.log_info(f"工作階段已結束: {self.session_id} ({status})")
            
        except Error as e:
            self.logger.log_error(e, "end_session")
    
    def insert_records(self, records: List[Dict]) -> int:
        """
        批量插入門牌記錄
        
        Args:
            records: 記錄列表
            
        Returns:
            成功插入的記錄數
        """
        if not records:
            return 0
        
        inserted_count = 0
        
        try:
            cursor = self.connection.cursor()
            
            sql = """
                INSERT INTO household_records 
                (city, district, village, neighbor, road, address_number, 
                 edit_date, edit_type, reason, remark, raw_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            
            for record in records:
                try:
                    values = (
                        record.get("city", ""),
                        record.get("district", ""),
                        record.get("village", ""),
                        record.get("neighbor", ""),
                        record.get("road", ""),
                        record.get("address_number", ""),
                        record.get("edit_date", ""),
                        record.get("edit_type", ""),
                        record.get("reason", ""),
                        record.get("remark", ""),
                        json.dumps(record, ensure_ascii=False)
                    )
                    cursor.execute(sql, values)
                    inserted_count += 1
                    
                except Error as e:
                    self.logger.log_debug(f"插入記錄失敗: {e}")
                    continue
            
            self.connection.commit()
            cursor.close()
            
            self.logger.log_info(f"成功插入 {inserted_count}/{len(records)} 筆記錄")
            
        except Error as e:
            self.logger.log_error(e, "insert_records")
            self.connection.rollback()
        
        return inserted_count
    
    def get_record_count(self) -> int:
        """取得總記錄數"""
        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM household_records")
            count = cursor.fetchone()[0]
            cursor.close()
            return count
        except Error:
            return 0
    
    def get_district_statistics(self) -> List[Dict]:
        """取得各區域統計"""
        try:
            cursor = self.connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM v_district_statistics")
            results = cursor.fetchall()
            cursor.close()
            return results
        except Error as e:
            self.logger.log_error(e, "get_district_statistics")
            return []
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()
