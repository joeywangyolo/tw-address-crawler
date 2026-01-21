# 戶政門牌資料爬蟲系統

自動爬取戶政門牌編釘資料的爬蟲系統，提供 REST API 介面及排程功能。

---

## 目錄

- [系統需求](#系統需求)
- [快速開始（Docker）](#快速開始docker)
- [本機執行（不使用 Docker）](#本機執行不使用-docker)
- [服務網址與登入資訊](#服務網址與登入資訊)
- [API 端點說明](#api-端點說明)
- [環境變數設定](#環境變數設定)
- [常用指令](#常用指令)
- [專案結構](#專案結構)
- [常見問題](#常見問題)

---

## 系統需求

### 使用 Docker（推薦）

- **Docker** 和 **Docker Compose**
- 不需要安裝 Python（容器內已包含）

| 作業系統 | 安裝方式 |
|---------|---------|
| **Windows** | 下載 [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Mac** | 下載 [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Linux** | `sudo apt install docker.io docker-compose` |

### 本機執行（不使用 Docker）

- **Python 3.9+**
- **MySQL 8.0**（可選，若不需資料庫功能可跳過）

---

## 快速開始（Docker）

### Step 1: Clone 專案

```bash
git clone https://github.com/joeywangyolo/tw-address-crawler.git
cd tw-address-crawler
```

### Step 2: 啟動所有服務

```bash
docker-compose up -d
```

首次啟動會自動：
- 下載 Python、MySQL、phpMyAdmin 映像檔
- 建立資料庫並執行初始化 SQL
- 啟動 API 服務與排程器

### Step 3: 確認服務運作

```bash
docker-compose ps
```

應顯示三個服務都是 `Up` 狀態：

```
NAME                  STATUS
household-api         Up
household-mysql       Up (healthy)
household-phpmyadmin  Up
```

### Step 4: 測試 API

開啟瀏覽器前往 http://localhost:8000/docs 即可看到 Swagger UI 互動式文件。

### Step 5: 進入容器手動執行爬蟲（可選）

如果想在 Docker 容器內手動執行爬蟲程式：

```bash
# 進入 API 容器的 shell
docker exec -it household-api bash

# 執行爬蟲程式
python crawler_requests.py

# 執行完畢後離開容器
exit
```

或直接一行指令執行（不進入容器）：

```bash
docker exec household-api python crawler_requests.py
```

> **PowerShell / CMD / Terminal 皆適用**

---

## 本機執行（不使用 Docker）

如果想在本機直接執行 Python 程式碼，請按以下步驟操作：

### Step 1: 安裝 Python 依賴

```bash
cd tw-address-crawler
pip install -r requirements.txt
```

### Step 2: 執行爬蟲程式（單次執行）

```bash
python crawler_requests.py
```

這會直接執行一次爬蟲，查詢所有台北市行政區的門牌資料，結果會：
- 輸出到終端機
- 儲存為 CSV 檔案於 `output/` 資料夾

### Step 3: 啟動 API 服務（可選）

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

啟動後可前往 http://localhost:8000/docs 使用 API。

> **注意**：本機執行 API 時，若未啟動 MySQL，資料庫相關功能會自動停用，但爬蟲核心功能仍可正常運作。

---

## 服務網址與登入資訊

### 服務列表

| 服務 | 網址 | 說明 |
|-----|------|------|
| **API 根目錄** | http://localhost:8000 | 爬蟲 API |
| **API 文件 (Swagger)** | http://localhost:8000/docs | 互動式 API 測試介面 |
| **API 文件 (ReDoc)** | http://localhost:8000/redoc | 靜態 API 文件 |
| **phpMyAdmin** | http://localhost:8080 | MySQL 資料庫管理介面 |

### phpMyAdmin 登入資訊

| 項目 | 值 |
|-----|-----|
| **網址** | http://localhost:8080 |
| **帳號** | `root` |
| **密碼** | `household123` |

> 若有在 `.env` 檔案修改 `MYSQL_PASSWORD`，請使用修改後的密碼登入。

---

## API 端點說明

所有 API 端點皆以 `/api/v1` 為前綴。

### 系統相關

| 方法 | 路徑 | 說明 |
|-----|------|------|
| `GET` | `/` | API 根目錄，顯示基本資訊與文件連結 |
| `GET` | `/api/v1/health` | 健康檢查，回傳 API 與資料庫連線狀態 |

### 查詢相關

| 方法 | 路徑 | 說明 |
|-----|------|------|
| `GET` | `/api/v1/districts` | 取得所有支援的行政區列表及代碼 |
| `POST` | `/api/v1/query/batch` | 批量查詢多個行政區的門牌資料 |

#### `POST /api/v1/query/batch` 批量查詢

**請求參數：**

| 欄位 | 類型 | 必填 | 預設值 | 說明 |
|-----|------|:----:|-------|------|
| `start_date` | string | ✅ | - | 起始日期，**民國年格式**：`114-09-01` |
| `end_date` | string | ✅ | - | 結束日期，**民國年格式**：`114-11-30` |
| `city_code` | string | ❌ | `"63000000"` | 縣市代碼（目前僅支援台北市） |
| `register_kind` | string | ❌ | `"1"` | 編釘類別：`1`=初編, `2`=改編, `3`=廢止, `4`=復用 |
| `districts` | array | ❌ | `null`（全部） | 指定行政區列表， **直接移除該欄位（不傳入）**表示查詢全部 12 區 |
| `save_to_db` | boolean | ❌ | `true` | 是否將結果存入資料庫 |



**支援的行政區：**

```
松山區、信義區、大安區、中山區、中正區、大同區、
萬華區、文山區、南港區、內湖區、士林區、北投區
```

**請求範例：**

```json
{
  "start_date": "114-09-01",
  "end_date": "114-11-30",
  "register_kind": "1",
  "districts": ["中正區", "大安區"],
  "save_to_db": true
}
```

**回應範例：**

```json
{
  "success": true,
  "total_count": 42,
  "district_results": {
    "中正區": 20,
    "大安區": 22
  },
  "failed_districts": [],
  "execution_time": 15.32,
  "data": [...],
  "error_message": null
}
```

| 回應欄位 | 說明 |
|---------|------|
| `success` | 查詢是否成功 |
| `total_count` | 總資料筆數 |
| `district_results` | 各行政區查詢到的筆數 |
| `failed_districts` | 查詢失敗的行政區列表 |
| `execution_time` | 執行時間（秒） |
| `data` | 門牌資料陣列（超過 300 筆時不返回） |
| `error_message` | 錯誤訊息（成功時為 null） |

### 排程相關

| 方法 | 路徑 | 說明 |
|-----|------|------|
| `GET` | `/api/v1/scheduler/status` | 查看排程器狀態與下次執行時間 |

### 使用範例

```bash
# 健康檢查
curl http://localhost:8000/api/v1/health

# 取得行政區列表
curl http://localhost:8000/api/v1/districts

# 查看排程狀態
curl http://localhost:8000/api/v1/scheduler/status

# 批量查詢（使用預設參數）
curl -X POST http://localhost:8000/api/v1/query/batch \
  -H "Content-Type: application/json" \
  -d '{"start_date": "114-09-01", "end_date": "114-11-30", "districts": ["中正區", "大安區"]}'
```

---

## 環境變數設定

所有設定都在 `docker-compose.yml` 中直接修改，無需額外設定檔案即可啟動。

### 可設定項目（編輯 `docker-compose.yml` 中的 `api` 服務 `environment` 區塊）

| 變數 | 預設值 | 說明 |
|-----|-------|------|
| `MYSQL_PASSWORD` | `household123` | MySQL root 密碼 |
| `ENABLE_SCHEDULER` | `true` | 是否啟用自動排程 |
| `SCHEDULE_MODE` | `cron` | 排程模式：`cron`（固定時間）或 `interval`（間隔執行） |
| `SCHEDULE_HOUR` | `17` | Cron 模式：執行時間（小時，0-23） |
| `SCHEDULE_MINUTE` | `17` | Cron 模式：執行時間（分鐘，0-59） |
| `SCHEDULE_INTERVAL_HOURS` | `1` | Interval 模式：間隔小時數 |
| `NOTIFICATION_ENABLED` | `false` | 是否啟用 Email 通知 |
| `SMTP_USER` | - | 寄件人 Email（Gmail 需使用應用程式密碼） |
| `SMTP_PASSWORD` | - | Email 密碼或應用程式密碼 |

---

## 排程功能說明

使用 **APScheduler** 實現自動排程功能，可在指定時間自動執行爬蟲任務。

### 排程模式

| 模式 | 說明 | 範例 |
|-----|------|------|
| `cron` | 固定時間執行（預設） | 每天 17:17 執行 |
| `interval` | 間隔執行 | 每 1 小時執行一次 |

### 設定方式

直接編輯 `docker-compose.yml` 中的 `api` 服務 `environment` 區塊：

```yaml
# 排程設定（如需修改請直接編輯此處）
- ENABLE_SCHEDULER=true
- SCHEDULE_MODE=cron
- SCHEDULE_HOUR=17
- SCHEDULE_MINUTE=17
```

### 查看排程狀態

```bash
curl http://localhost:8000/api/v1/scheduler/status
```

回應範例：

```json
{
  "enabled": true,
  "running": true,
  "schedule_time": "9:00",
  "jobs": [
    {
      "id": "cron_crawl",
      "name": "定時爬蟲任務",
      "next_run_time": "2025-01-22 09:00:00+08:00"
    }
  ]
}
```

---

## Email 通知功能

當爬蟲執行失敗或查詢結果為空時，系統會自動發送 Email 通知。

### Step 1: 取得 Gmail 應用程式密碼

Gmail 不允許直接使用帳號密碼登入 SMTP，需要使用「應用程式密碼」。

1. 前往 [Google 應用程式密碼](https://myaccount.google.com/apppasswords)
2. 登入你的 Google 帳號
3. 選擇應用程式：「郵件」
4. 選擇裝置：「Windows 電腦」或「其他」
5. 點擊「產生」，複製 16 位密碼

> ℹ️ 必須先啟用「兩步驗證」才能使用應用程式密碼

### Step 2: 設定環境變數

在 `.env` 或 `docker-compose.yml` 中設定：

```yaml
# 啟用通知
NOTIFICATION_ENABLED=true

# SMTP 設定（Gmail）
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx  # 應用程式密碼（16位）
```

### Step 3: 新增收件人

透過 phpMyAdmin 或 SQL 新增收件人：

1. 開啟 http://localhost:8080 (phpMyAdmin)
2. 選擇資料庫 `household_db`
3. 點選 `email_address` 表
4. 新增一筆資料：

```sql
INSERT INTO email_address (email, is_active) VALUES ('recipient@example.com', 1);
```

### Step 4: 測試發信功能

使用以下查詢條件（已知查無資料）來觸發「查詢資料為空」通知：

```bash
curl -X POST http://localhost:8000/api/v1/query/batch \
  -H "Content-Type: application/json" \
  -d '{
    "start_date": "114-09-01",
    "end_date": "114-11-30",
    "register_kind": "1",
    "districts": ["南港區"]
  }'
```

> 這個條件查無資料，會觸發系統發送「查詢資料為空」Email 通知。

---

### 本機執行

```bash
# 安裝套件
pip install -r requirements.txt

# 單次執行爬蟲
python crawler_requests.py

# 啟動 API 服務
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 專案結構

```
tw-address-crawler/
├── api/                    # FastAPI 應用程式
│   ├── main.py             # API 主程式與路由定義
│   └── schemas.py          # Pydantic 資料模型
├── database/               # 資料庫相關
│   ├── db_manager.py       # 資料庫連線與操作
│   └── init.sql            # 資料庫初始化 SQL
├── utils/                  # 工具模組
│   └── notifier.py         # Email 通知功能
├── logs/                   # Log 檔案（自動產生）
├── output/                 # CSV 輸出檔案（自動產生）
├── crawler_requests.py     # 爬蟲核心邏輯
├── Dockerfile              # Docker 映像檔定義
├── docker-compose.yml      # Docker Compose 服務編排
├── requirements.txt        # Python 依賴套件
├── .env.example            # 環境變數範例
└── README.md               # 本文件
```

---

## 常見問題

### Q: 啟動失敗，顯示 port 已被使用？

修改 `docker-compose.yml` 中的 port 映射：

```yaml
# API 服務改用 8001
ports:
  - "8001:8000"

# phpMyAdmin 改用 8081
ports:
  - "8081:80"
```


### Q: 如何查看爬蟲執行結果？

1. **查看 CSV 輸出**：`output/` 資料夾
2. **查看資料庫**：http://localhost:8080 (phpMyAdmin)
3. **查看 Log**：`docker-compose logs -f api`
4. **每次執行的Log 會記錄於**: 資料庫的 `crawler_logs` 表格中

### Q: 驗證碼識別失敗怎麼辦？

系統使用 `ddddocr` 自動識別驗證碼，識別率約 90%。失敗時會自動重試（最多 10 次）。若連續失敗，會在 Log 中顯示錯誤訊息。

### Q: 如何修改爬蟲的查詢日期範圍？

1. **透過 API**：呼叫 `/api/v1/query/batch` 時指定 `start_date` 和 `end_date`
2. **修改預設值**：編輯 `crawler_requests.py` 中的 `main()` 函數

### Q: 排程器沒有自動執行？

1. 確認 `ENABLE_SCHEDULER=true`
2. 檢查排程狀態：`curl http://localhost:8000/api/v1/scheduler/status`
3. 查看 Log 確認是否有錯誤訊息
