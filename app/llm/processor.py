"""
Обработка пользовательского запроса.
Парсинг, сжатие, работа с историей.
Не зависит от GigaChat — чистая трансформация данных.
"""

import json
from typing import List, Optional

from app.llm.client import ask_gigachat_generic
from app.cache import (
    get_cached_parse,
    cache_parse,
    get_cached_compressed,
    cache_compressed,
)
from app.core.logger import logger
from app.schemas import ParsedRequest, CompressedMessage
from app.services.prompts import PARSER_SYSTEM_PROMPT, COMPRESSOR_SYSTEM_PROMPT, AGENT_PARAMS


# ===== ПАРСИНГ ИСХОДНОГО ЗАПРОСА =====

def parse_user_request(user_msg: str, user_id: str = "anonymous") -> ParsedRequest:
    """
    Парсит исходный запрос пользователя в структурированную форму.
    
    Использует парсер промпт, который вытаскивает:
    - intent (валидировать идею, найти риски и т.д.)
    - domain (продукт, финансы, маркетинг и т.д.)
    - ключевые пункты
    - предположения
    - ограничения
    
    Результат кэшируется по user_id и сообщению.
    
    Args:
        user_msg: исходное сообщение пользователя
        user_id: идентификатор пользователя (для кэша)
        
    Returns:
        ParsedRequest: структурированный парс запроса
        
    Raises:
        requests.RequestException: если ошибка при запросе к GigaChat
    """
    # Проверяем кэш
    cached = get_cached_parse(user_id, user_msg)
    if cached:
        logger.info("Parser cache hit | user=%s | message=%s", user_id, user_msg[:50])
        return cached

    logger.info(
        "Parser: processing new request | user=%s | message=%s",
        user_id,
        user_msg[:50],
    )

    # Парсим через GigaChat используя универсальную функцию
    parser_output, usage = ask_gigachat_generic(
        system_prompt=PARSER_SYSTEM_PROMPT,
        user_msg=user_msg,
        temperature=0.3,
        max_tokens=300,
        top_p=0.85,
        track_usage=False,
    )

    logger.info(
        "Parser output | message=%s | output=%s | tokens=%d",
        user_msg[:50],
        parser_output[:200],
        usage.get("tokens_total", 0),
    )

    # Парсим JSON из ответа
    try:
        parsed_json = json.loads(parser_output)
    except json.JSONDecodeError:
        logger.warning("Parser output is not valid JSON: %s", parser_output)
        # Fallback если парсер сломался
        parsed_json = {
            "intent": "other",
            "domain": "strategy",
            "key_points": [user_msg[:200]],
            "assumptions": [],
            "constraints": [],
            "summary": user_msg[:200],
        }

    # Создаём ParsedRequest
    parsed = ParsedRequest(
        original_message=user_msg,
        intent=parsed_json.get("intent", "other"),
        domain=parsed_json.get("domain", "strategy"),
        key_points=parsed_json.get("key_points", []) or [],
        assumptions=parsed_json.get("assumptions", []) or [],
        constraints=parsed_json.get("constraints", []) or [],
        summary=parsed_json.get("summary"),
        confidence=0.85,
    )

    # Кэшируем результат
    cache_parse(user_id, user_msg, parsed)
    return parsed


# ===== СЖАТИЕ СООБЩЕНИЯ ПОЛЬЗОВАТЕЛЯ =====

def compress_user_message(user_msg: str, user_id: str = "anonymous") -> CompressedMessage:
    """
    Сжимает сообщение пользователя в структурированную выжимку (JSON).
    
    Использует компрессор промпт для преобразования текста в структуру:
    - intent, domain
    - idea_summary (суть в 1-2 предложениях)
    - key_points (главные факты)
    - constraints (бюджет, сроки, команда)
    - assumptions (предположения)
    - key_facts (важные факты)
    
    Результат кэшируется.
    
    Args:
        user_msg: исходное сообщение пользователя
        user_id: идентификатор пользователя (для кэша)
        
    Returns:
        CompressedMessage: структурированное и сжатое сообщение
        
    Raises:
        requests.RequestException: если ошибка при запросе к GigaChat
    """
    # Проверяем кэш
    cached = get_cached_compressed(user_id, user_msg)
    if cached:
        logger.info(
            "Compressed message cache hit | user=%s | message=%s",
            user_id,
            user_msg[:50],
        )
        return CompressedMessage(**cached)

    logger.info(
        "Compressor: processing new message | user=%s | message=%s",
        user_id,
        user_msg[:50],
    )

    # Сжимаем через GigaChat используя универсальную функцию
    compressor_output, usage = ask_gigachat_generic(
        system_prompt=COMPRESSOR_SYSTEM_PROMPT,
        user_msg=user_msg,
        temperature=AGENT_PARAMS["compressor"]["temperature"],
        max_tokens=AGENT_PARAMS["compressor"]["max_tokens"],
        top_p=AGENT_PARAMS["compressor"]["top_p"],
        track_usage=False,
    )

    logger.info(
        "Compressor output | message=%s | output=%s | tokens=%d",
        user_msg[:50],
        compressor_output[:200],
        usage.get("tokens_total", 0),
    )

    # Парсим JSON из ответа
    try:
        compressed_json = json.loads(compressor_output)

        # Валидируем наличие ключевых полей
        if not compressed_json or not compressed_json.get("intent") or not compressed_json.get("domain"):
            logger.warning("Compressor returned incomplete JSON: %s", compressed_json)
            compressed_json = {
                "intent": "other",
                "domain": "strategy",
                "idea_summary": user_msg[:100],
                "key_points": [user_msg[:200]],
                "constraints": None,
                "assumptions": [],
                "key_facts": []
            }
    except json.JSONDecodeError:
        logger.warning("Compressor output is not valid JSON: %s", compressor_output)
        # Fallback
        compressed_json = {
            "intent": "other",
            "domain": "strategy",
            "idea_summary": user_msg[:100],
            "key_points": [user_msg[:200]],
            "constraints": None,
            "assumptions": [],
            "key_facts": []
        }

    # Создаём CompressedMessage
    compressed = CompressedMessage(**compressed_json)

    # Кэшируем результат
    cache_compressed(user_id, user_msg, compressed.dict())

    return compressed


# ===== СЖАТИЕ ИСТОРИИ =====

def compress_history(history: Optional[List[str]], max_items: int = 15) -> str:
    """
    Сжимает историю диалога до последних N сообщений.
    
    Используется для экономии токенов при включении истории в контекст агента.
    Берёт только последние max_items сообщений и объединяет их в строку.
    
    Args:
        history: список сообщений (может быть None или пусто)
        max_items: максимум сообщений для сохранения
        
    Returns:
        str: сжатая история (multi-line string) или пустая строка
    """
    if not history:
        return ""
    
    # Берём только последние max_items
    recent = history[-max_items:]
    
    # Объединяем в строку с переносами
    compressed = "\n".join(recent)
    
    logger.debug(
        "History compressed | original_len=%d | kept=%d | output_len=%d",
        len(history),
        len(recent),
        len(compressed),
    )
    
    return compressed


__all__ = [
    "parse_user_request",
    "compress_user_message",
    "compress_history",
]
