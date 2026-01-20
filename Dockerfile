# 戶政門牌資料爬蟲 API
FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴（包含 ddddocr 需要的 OpenCV 依賴）
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴檔案
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 複製專案檔案
COPY . .

# 建立必要目錄
RUN mkdir -p logs output

# 暴露端口
EXPOSE 8000

# 啟動命令
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
