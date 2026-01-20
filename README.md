# 戶政門牌資料爬蟲系統

自動爬取戶政門牌編釘資料的爬蟲系統，提供 REST API 介面及排程功能。

## 系統需求

- **Docker** 和 **Docker Compose**
- 不需要安裝 Python（容器內已包含）

### 安裝 Docker

| 作業系統 | 安裝方式 |
|---------|---------|
| **Windows** | 下載 [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Mac** | 下載 [Docker Desktop](https://www.docker.com/products/docker-desktop/) |
| **Linux** | `sudo apt install docker.io docker-compose` |

---

## 快速開始

### 1. Clone 專案

```bash
git clone https://github.com/your-username/household-crawler.git
cd household-crawler
```

### 2. 啟動服務

```bash
docker-compose up -d
```

首次啟動會自動：
- 下載 Python、MySQL、phpMyAdmin 映像檔
- 建立資料庫並執行初始化 SQL
- 啟動 API 服務

### 3. 確認服務運作

```bash
docker-compose ps
```

所有服務都顯示 `Up` 即表示成功。

---

## 服務網址

| 服務 | 網址 | 說明 |
|-----|------|------|
| **API** | http://localhost:8000 | 爬蟲 API |
| **API 文件** | http://localhost:8000/docs | Swagger UI |
| **phpMyAdmin** | http://localhost:8080 | 資料庫管理介面 |

---

## 基本操作

### 執行爬蟲（手動觸發）

```bash
# 透過 API 觸發
curl -X POST http://localhost:8000/trigger-crawl

# 或在瀏覽器開啟 http://localhost:8000/docs 點擊 "Try it out"
```

### 查看 Log

```bash
docker-compose logs -f api
```

### 停止服務

```bash
docker-compose down
```

### 停止並清除資料

```bash
docker-compose down -v
```

---

## 環境變數設定（可選）

複製 `.env.example` 為 `.env` 來自訂設定：

```bash
cp .env.example .env
```

可設定項目：

| 變數 | 預設值 | 說明 |
|-----|-------|------|
| `MYSQL_PASSWORD` | `household123` | 資料庫密碼 |
| `ENABLE_SCHEDULER` | `true` | 啟用排程 |
| `SCHEDULE_MODE` | `cron` | 排程模式 (`cron` 或 `interval`) |
| `SCHEDULE_HOUR` | `2` | Cron 模式：執行時間（小時） |
| `SCHEDULE_MINUTE` | `0` | Cron 模式：執行時間（分鐘） |

---

## API 端點

| 方法 | 路徑 | 說明 |
|-----|------|------|
| `GET` | `/health` | 健康檢查 |
| `GET` | `/scheduler/status` | 排程狀態 |
| `POST` | `/trigger-crawl` | 手動觸發爬蟲 |
| `POST` | `/batch-query` | 批量查詢（自訂參數） |
| `GET` | `/districts` | 取得行政區列表 |
| `GET` | `/records` | 查詢資料庫記錄 |

完整 API 文件請參考 http://localhost:8000/docs

---

## 專案結構

```
household-crawler/
├── api/                  # FastAPI 應用程式
│   └── main.py
├── database/             # 資料庫相關
│   ├── db_manager.py
│   └── init.sql
├── docs/                 # 文件與流程圖
├── logs/                 # Log 檔案（自動產生）
├── output/               # CSV 輸出（自動產生）
├── crawler_requests.py   # 爬蟲核心邏輯
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## 常見問題

### Q: 啟動失敗，顯示 port 已被使用？

修改 `docker-compose.yml` 中的 port 映射：
```yaml
ports:
  - "8001:8000"  # 改用 8001
```

### Q: Mac M1/M2 晶片可以用嗎？

可以，Docker Desktop 支援 Apple Silicon。

### Q: 如何查看資料庫內容？

開啟 http://localhost:8080 (phpMyAdmin)
- 帳號: `root`
- 密碼: `household123`（或你在 `.env` 設定的密碼）
