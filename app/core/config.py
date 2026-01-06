"""
Централизованная конфигурация приложения.
Все константы, переменные окружения и параметры в одном месте.
"""

import os
from dotenv import load_dotenv

# Загружаем .env файл
load_dotenv()

# ===== LOGGING =====
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "gigachat.log")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
LOG_LEVEL = "INFO"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 3

# ===== GIGACHAT API =====
GIGA_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGA_API_BASE = "https://gigachat.devices.sberbank.ru"
GIGA_SCOPE = "GIGACHAT_API_PERS"
GIGA_MODEL = "GigaChat-2"
GIGA_REQUEST_TIMEOUT = 60  # секунды

GIGA_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")
if not GIGA_AUTH_KEY:
    raise RuntimeError(
        "Не задана переменная окружения GIGACHAT_AUTH_KEY. "
        "Установите её перед запуском приложения."
    )

# ===== JWT (из auth.py) =====
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError(
        "Не задана переменная окружения JWT_SECRET_KEY. "
        "Установите её перед запуском приложения."
    )

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # Короткоживущий
REFRESH_TOKEN_EXPIRE_DAYS = 30    # Долгоживущий

# ===== DATABASE (из db.py) =====
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "Не задана переменная окружения DATABASE_URL. "
        "Установите её перед запуском приложения."
    )

# ===== CORS =====
CORS_ORIGINS = [
    "http://45.151.31.180:8080",
    "http://localhost:8080",
    "http://localhost:3000",
]

# ===== RATE LIMITING =====
RATE_LIMIT_BOARD_CHAT = "10/minute"      # POST /api/board
RATE_LIMIT_SINGLE_AGENT = "20/minute"    # POST /api/agent
RATE_LIMIT_SUMMARY = "10/minute"         # POST /api/summary

# ===== CACHING =====
CACHE_MAX_ITEMS = 1000           # максимум записей в кэше
CACHE_CLEANUP_SIZE = 500         # оставлять при очистке
