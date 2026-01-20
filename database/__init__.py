# 資料庫模組
# db_manager.py 使用 pymysql，是主要使用的模組
# db_handler.py 是舊版，使用 mysql.connector（已棄用）

try:
    from .db_manager import DatabaseManager, DBConfig, EDIT_TYPE_MAPPING
except ImportError:
    pass
