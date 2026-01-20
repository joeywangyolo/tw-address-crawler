-- 戶政司門牌查詢資料庫初始化腳本
-- 建立時會自動執行

-- 使用資料庫
USE household_db;

-- 設定字元集
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ============================================================
-- 爬蟲執行記錄表：記錄每次 API 呼叫的基本 log
-- 此表的 id 作為 batch_id，關聯其他表的資料
-- ============================================================
CREATE TABLE IF NOT EXISTS crawler_logs (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '批次 ID (batch_id)',
    api_endpoint VARCHAR(100) COMMENT 'API 端點',
    start_time DATETIME COMMENT '開始時間',
    end_time DATETIME COMMENT '結束時間',
    records_fetched INT DEFAULT 0 COMMENT '擷取記錄數',
    status ENUM('running', 'completed', 'failed') DEFAULT 'running' COMMENT '狀態',
    error_message TEXT COMMENT '錯誤訊息',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
    INDEX idx_status (status),
    INDEX idx_start_time (start_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='爬蟲執行記錄表';

-- ============================================================
-- 門牌資料表：儲存查詢到的門牌資料
-- ============================================================
CREATE TABLE IF NOT EXISTS household_records (
    id INT AUTO_INCREMENT PRIMARY KEY,
    batch_id INT COMMENT '批次 ID，關聯 crawler_logs.id',
    city VARCHAR(50) COMMENT '縣市',
    district VARCHAR(50) COMMENT '區域',
    full_address VARCHAR(500) COMMENT '完整地址',
    edit_date VARCHAR(20) COMMENT '編訂日期',
    edit_type_code VARCHAR(10) COMMENT '編訂類別代碼',
    edit_type_name VARCHAR(50) COMMENT '編訂類別名稱',
    raw_data JSON COMMENT '原始資料(JSON格式)',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
    INDEX idx_batch_id (batch_id),
    INDEX idx_city_district (city, district),
    INDEX idx_edit_date (edit_date),
    INDEX idx_edit_type_code (edit_type_code),
    FOREIGN KEY (batch_id) REFERENCES crawler_logs(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='門牌資料表';

-- ============================================================
-- 行政區查詢結果表：記錄每個行政區的查詢結果
-- ============================================================
CREATE TABLE IF NOT EXISTS district_query_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    batch_id INT COMMENT '批次 ID，關聯 crawler_logs.id',
    city_name VARCHAR(50) COMMENT '城市名稱',
    district_code VARCHAR(20) COMMENT '行政區代碼',
    district_name VARCHAR(50) COMMENT '行政區名稱',
    record_count INT DEFAULT 0 COMMENT '查詢到的筆數',
    status ENUM('success', 'failed', 'no_data') DEFAULT 'success' COMMENT '狀態',
    error_message TEXT COMMENT '錯誤訊息',
    queried_at DATETIME COMMENT '查詢時間',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
    INDEX idx_batch_id (batch_id),
    INDEX idx_district_name (district_name),
    INDEX idx_queried_at (queried_at),
    FOREIGN KEY (batch_id) REFERENCES crawler_logs(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='行政區查詢結果表';

-- ============================================================
-- 通知信箱表：儲存接收異常通知的 Email 地址
-- ============================================================
CREATE TABLE IF NOT EXISTS email_address (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL COMMENT 'Email 地址',
    name VARCHAR(100) COMMENT '收件人名稱',
    is_active BOOLEAN DEFAULT TRUE COMMENT '是否啟用',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '建立時間',
    UNIQUE KEY uk_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='通知信箱表';

-- 插入預設的通知信箱（請自行修改）
-- INSERT INTO email_address (email, name) VALUES ('your-email@example.com', '管理員');

-- 顯示建立結果
SELECT 'Database initialized successfully!' as message;
SHOW TABLES;
