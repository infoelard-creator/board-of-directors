"""
Конфигурация логирования для приложения.
Предоставляет готовый logger для всех модулей.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
from app.core.config import LOG_DIR, LOG_FILE, LOG_FORMAT, LOG_LEVEL, LOG_MAX_BYTES, LOG_BACKUP_COUNT

# Создаём директорию для логов, если не существует
os.makedirs(LOG_DIR, exist_ok=True)

# Создаём логгер
logger = logging.getLogger("gigachat")
logger.setLevel(getattr(logging, LOG_LEVEL))

# Обработчик с ротацией файлов
handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding="utf-8",
)

# Форматер
formatter = logging.Formatter(LOG_FORMAT)
handler.setFormatter(formatter)

# Добавляем обработчик к логгеру
logger.addHandler(handler)

__all__ = ["logger"]
