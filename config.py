import os


DB_HOST = os.getenv("GBDD_DB_HOST", "localhost")
DB_PORT = int(os.getenv("GBDD_DB_PORT", "5432"))
DB_NAME = os.getenv("GBDD_DB_NAME", "gbdd_db")
DB_USER = os.getenv("GBDD_DB_USER", "postgres")
DB_PASSWORD = os.getenv("GBDD_DB_PASSWORD", "1234")
DB_CONNECT_TIMEOUT = int(os.getenv("GBDD_DB_CONNECT_TIMEOUT", "10"))
