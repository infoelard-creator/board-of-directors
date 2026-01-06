"""
Управление кэшем для парсера и компрессора сообщений.
Использует in-memory словари с потокобезопасностью (Lock).
"""

import hashlib
from typing import Optional, Dict
from threading import Lock
from app.schemas import ParsedRequest, CompressedMessage
from app.core.logger import logger
from app.core.config import CACHE_MAX_ITEMS, CACHE_CLEANUP_SIZE

# Глобальные кэши
_parsed_cache: Dict[str, ParsedRequest] = {}
_compressed_cache: Dict[str, dict] = {}
_cache_lock = Lock()


def get_cache_key(user_id: str, message: str) -> str:
    """Генерирует ключ кэша на основе user_id и сообщения."""
    msg_hash = hashlib.md5(message.encode()).hexdigest()[:8]
    return f"{user_id}:{msg_hash}"


def get_cached_parse(user_id: str, message: str) -> Optional[ParsedRequest]:
    """Получает кэшированный парс запроса."""
    with _cache_lock:
        key = get_cache_key(user_id, message)
        cached = _parsed_cache.get(key)
        if cached:
            logger.info("Parser cache hit | user=%s | message=%s", user_id, message[:50])
        return cached


def cache_parse(user_id: str, message: str, parsed: ParsedRequest) -> None:
    """Кэширует парс запроса."""
    with _cache_lock:
        key = get_cache_key(user_id, message)
        _parsed_cache[key] = parsed
        if len(_parsed_cache) > CACHE_MAX_ITEMS:
            keys_to_delete = list(_parsed_cache.keys())[:-CACHE_CLEANUP_SIZE]
            for k in keys_to_delete:
                del _parsed_cache[k]
            logger.info("Parser cache cleaned | remaining=%d", len(_parsed_cache))


def get_cached_compressed(user_id: str, message: str) -> Optional[dict]:
    """Получает кэшированное сжатое сообщение."""
    with _cache_lock:
        key = get_cache_key(user_id, message)
        return _compressed_cache.get(key)


def cache_compressed(user_id: str, message: str, compressed: dict) -> None:
    """Кэширует сжатое сообщение."""
    with _cache_lock:
        key = get_cache_key(user_id, message)
        _compressed_cache[key] = compressed
        if len(_compressed_cache) > CACHE_MAX_ITEMS:
            keys_to_delete = list(_compressed_cache.keys())[:-CACHE_CLEANUP_SIZE]
            for k in keys_to_delete:
                del _compressed_cache[k]
            logger.info("Compressed cache cleaned | remaining=%d", len(_compressed_cache))


def clear_all_caches() -> None:
    """Очищает все кэши (для тестирования и управления памятью)."""
    with _cache_lock:
        _parsed_cache.clear()
        _compressed_cache.clear()
        logger.info("All caches cleared")


__all__ = [
    "get_cache_key",
    "get_cached_parse",
    "cache_parse",
    "get_cached_compressed",
    "cache_compressed",
    "clear_all_caches",
]
