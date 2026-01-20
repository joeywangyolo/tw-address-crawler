"""
異常通知模組
當爬蟲發生錯誤或查詢資料為空時，發送 Email 通知
"""

import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class EmailNotifier:
    """Email 通知器"""
    
    def __init__(self):
        """
        初始化 Email 通知器
        需要設定環境變數：
        - SMTP_HOST: SMTP 伺服器 (預設 smtp.gmail.com)
        - SMTP_PORT: SMTP 埠號 (預設 587)
        - SMTP_USER: 寄件人 Email
        - SMTP_PASSWORD: 寄件人密碼或應用程式密碼
        - NOTIFICATION_ENABLED: 是否啟用通知 (true/false)
        """
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.enabled = os.getenv("NOTIFICATION_ENABLED", "false").lower() == "true"
    
    def is_configured(self) -> bool:
        """檢查是否已設定 SMTP"""
        return bool(self.smtp_user and self.smtp_password)
    
    def send_email(
        self,
        to_emails: List[str],
        subject: str,
        body: str
    ) -> bool:
        """
        發送 Email
        
        參數:
            to_emails: 收件人 Email 列表
            subject: 主旨
            body: 內容
            
        回傳:
            bool: 是否發送成功
        """
        if not self.enabled:
            logger.debug("通知功能未啟用 (NOTIFICATION_ENABLED=false)")
            return False
        
        if not self.is_configured():
            logger.warning("SMTP 未設定，無法發送通知")
            return False
        
        if not to_emails:
            logger.warning("沒有收件人，無法發送通知")
            return False
        
        try:
            msg = MIMEMultipart()
            msg["From"] = self.smtp_user
            msg["To"] = ", ".join(to_emails)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain", "utf-8"))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_user, to_emails, msg.as_string())
            
            logger.info(f"通知已發送給: {', '.join(to_emails)}")
            return True
            
        except Exception as e:
            logger.error(f"發送通知失敗: {e}")
            return False
    
    def notify_crawler_error(
        self,
        to_emails: List[str],
        error_message: str,
        batch_id: Optional[int] = None
    ) -> bool:
        """
        發送爬蟲錯誤通知
        
        參數:
            to_emails: 收件人 Email 列表
            error_message: 錯誤訊息
            batch_id: 批次 ID
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subject = f"[戶政爬蟲] 異常通知 - 爬蟲執行失敗"
        
        body = f"""
戶政門牌爬蟲系統 - 異常通知

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ 異常類型: 爬蟲執行失敗
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

發生時間: {timestamp}
批次 ID: {batch_id if batch_id else 'N/A'}

錯誤訊息:
{error_message}

請檢查系統狀態。

---
此信件由系統自動發送
        """.strip()
        
        return self.send_email(to_emails, subject, body)
    
    def notify_empty_data(
        self,
        to_emails: List[str],
        query_info: str,
        batch_id: Optional[int] = None
    ) -> bool:
        """
        發送查詢資料為空通知
        
        參數:
            to_emails: 收件人 Email 列表
            query_info: 查詢資訊
            batch_id: 批次 ID
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subject = f"[戶政爬蟲] 異常通知 - 查詢資料為空"
        
        body = f"""
戶政門牌爬蟲系統 - 異常通知

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📭 異常類型: 查詢資料為空
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

發生時間: {timestamp}
批次 ID: {batch_id if batch_id else 'N/A'}

查詢資訊:
{query_info}

這可能表示指定日期範圍內沒有新的門牌資料，
或者爬蟲無法正確取得資料。

請確認查詢條件是否正確。

---
此信件由系統自動發送
        """.strip()
        
        return self.send_email(to_emails, subject, body)


# 全域通知器實例
notifier = EmailNotifier()
