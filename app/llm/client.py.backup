"""
GigaChat API клиент.
Отвечает за получение токенов, отправку запросов и разворачивание ответов.
Не знает про бизнес-логику — чистый транспортный слой.
"""

import os
import uuid
import time
import json
import requests
from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
from threading import Lock
import urllib3

from app.core.config import (
    GIGA_AUTH_URL,
    GIGA_API_BASE,
    GIGA_SCOPE,
    GIGA_AUTH_KEY,
    GIGA_MODEL,
    GIGA_REQUEST_TIMEOUT,
)
from app.core.logger import logger
from app.schemas import DebugMetadata
from app.services.prompts import AGENT_SYSTEM_PROMPTS, AGENT_PARAMS, EXPANDER_SYSTEM_PROMPT

# Отключаем warnings для self-signed сертификатов
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ===== ГЛОБАЛЬНОЕ СОСТОЯНИЕ ТОКЕНА =====

_access_token: Optional[str] = None
_access_exp: Optional[datetime] = None
_token_lock = Lock()


# ===== ПОЛУЧЕНИЕ ТОКЕНА =====

def get_gigachat_token() -> str:
    """
    Получает или обновляет JWT токен доступа к GigaChat API.
    
    Использует глобальное состояние с lock для потокобезопасности.
    Кэширует токен и обновляет только если истёк.
    
    Returns:
        JWT токен для авторизации в GigaChat API
        
    Raises:
        RuntimeError: если не удалось получить токен (ошибка Sber API)
    """
    global _access_token, _access_exp

    with _token_lock:
        # Если токен ещё валидный — возвращаем его
        if _access_token and _access_exp and datetime.now(timezone.utc) < _access_exp:
            return _access_token

        # Готовим заголовки для запроса
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {GIGA_AUTH_KEY}",
        }
        data = {"scope": GIGA_SCOPE}

        logger.info(
            "Auth request -> %s | RqUID=%s",
            GIGA_AUTH_URL,
            headers["RqUID"],
        )

        # Отправляем запрос на получение токена
        resp = requests.post(
            GIGA_AUTH_URL,
            headers=headers,
            data=data,
            timeout=10,
            verify=False,  # Sber использует self-signed сертификат
        )

        logger.info(
            "Auth response <- %s | status=%s",
            GIGA_AUTH_URL,
            resp.status_code,
        )

        # Обработка ошибок
        if resp.status_code != 200:
            logger.error("Auth failed | status=%s | body=%s", resp.status_code, resp.text)
            resp.raise_for_status()

        j = resp.json()
        _access_token = j["access_token"]
        
        # Токен действует ~30 минут, ставим expiry на 25 минут (с запасом)
        _access_exp = datetime.now(timezone.utc) + timedelta(minutes=25)

        logger.info("Auth successful | expires_at=%s", _access_exp.isoformat())

    return _access_token


# ===== ОСНОВНОЙ ЗАПРОС К GIGACHAT =====

def ask_gigachat(
    agent: str,
    user_msg: str,
    track_usage: bool = False,
) -> Tuple[str, dict]:
    """
    Отправляет запрос к GigaChat API и получает ответ от агента.
    
    Args:
        agent: имя агента (ceo, cfo, cpo, marketing, skeptic, summary)
        user_msg: сообщение пользователя (уже должно содержать сжатый контекст)
        track_usage: нужно ли логировать детали использования токенов
        
    Returns:
        Tuple[str, dict]: (текст ответа, словарь с usage метриками)
        
    Raises:
        KeyError: если agent не в AGENT_SYSTEM_PROMPTS
        requests.RequestException: если ошибка при запросе к API
    """
    token = get_gigachat_token()
    system_prompt = AGENT_SYSTEM_PROMPTS[agent]
    params = AGENT_PARAMS[agent]

    # Готовим payload для API
    payload = {
        "model": GIGA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "temperature": params["temperature"],
        "max_tokens": params["max_tokens"],
        "top_p": params["top_p"],
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    url = f"{GIGA_API_BASE}/api/v1/chat/completions"

    start_time = time.time()

    logger.info(
        "Chat request -> %s | agent=%s | temp=%.1f | max_tokens=%d",
        url,
        agent,
        params["temperature"],
        params["max_tokens"],
    )

    # Отправляем запрос
    resp = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=GIGA_REQUEST_TIMEOUT,
        verify=False,
    )

    latency_ms = (time.time() - start_time) * 1000

    logger.info(
        "Chat response <- %s | agent=%s | status=%s | latency=%.0fms",
        url,
        agent,
        resp.status_code,
        latency_ms,
    )

    # Обработка ошибок
    if resp.status_code != 200:
        logger.error(
            "Chat request failed | agent=%s | status=%s | body=%s",
            agent,
            resp.status_code,
            resp.text[:500],
        )
        resp.raise_for_status()

    j = resp.json()

    # Извлекаем данные из ответа
    finish_reason = j.get("choices", [{}])[0].get("finish_reason", "unknown")
    tokens_input, tokens_output, tokens_total = _extract_usage(j)

    usage_dict = {
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "tokens_total": tokens_total,
        "finish_reason": finish_reason,
        "latency_ms": latency_ms,
    }

    response_text = j["choices"][0]["message"]["content"].strip()

    if track_usage:
        logger.info(
            "Usage | agent=%s | tokens_in=%d | tokens_out=%d | total=%d | finish_reason=%s",
            agent,
            tokens_input,
            tokens_output,
            tokens_total,
            finish_reason,
        )

    return response_text, usage_dict


# ===== РАЗВОРАЧИВАНИЕ СЖАТОГО ОТВЕТА =====

def expand_agent_output(
    agent: str,
    compressed_output: dict,
    track_usage: bool = False,
) -> Tuple[str, dict]:
    """
    Преобразует сжатый JSON-ответ агента в читаемый текст.
    
    Использует специальный "expander" промпт, который знает как
    форматировать разные типы вердиктов для фронтенда.
    
    Args:
        agent: имя агента (для контекста в expander промпте)
        compressed_output: сжатый JSON ответ агента
        track_usage: нужно ли логировать метрики
        
    Returns:
        Tuple[str, dict]: (расширенный текст, usage словарь)
        
    Raises:
        requests.RequestException: если ошибка при запросе к API
    """
    token = get_gigachat_token()

    # Словарь с описанием ролей для контекста
    AGENT_ROLES = {
        "ceo": "CEO (стратегический лидер компании)",
        "cfo": "CFO (финансовый директор)",
        "cpo": "CPO (директор по продукту)",
        "marketing": "VP Marketing (вице-президент маркетинга)",
        "skeptic": "Skeptic (критический аналитик)",
        "summary": "Summary (модератор совета)",
    }

    agent_role = AGENT_ROLES.get(agent, agent.upper())

    # Готовим payload
    payload = {
        "model": GIGA_MODEL,
        "messages": [
            {"role": "system", "content": EXPANDER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Роль агента: {agent_role}\n\n"
                    f"Вот сжатый ответ (JSON), разверни в читаемый текст:\n\n"
                    f"{json.dumps(compressed_output, ensure_ascii=False, indent=2)}"
                ),
            },
        ],
        "stream": False,
        "temperature": AGENT_PARAMS["expander"]["temperature"],
        "max_tokens": AGENT_PARAMS["expander"]["max_tokens"],
        "top_p": AGENT_PARAMS["expander"]["top_p"],
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    url = f"{GIGA_API_BASE}/api/v1/chat/completions"

    start_time = time.time()

    logger.info(
        "Expander request -> %s | agent=%s",
        url,
        agent,
    )

    # Отправляем запрос
    resp = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=GIGA_REQUEST_TIMEOUT,
        verify=False,
    )

    latency_ms = (time.time() - start_time) * 1000

    logger.info(
        "Expander response <- %s | agent=%s | latency=%.0fms",
        url,
        agent,
        latency_ms,
    )

    # Обработка ошибок
    if resp.status_code != 200:
        logger.error(
            "Expander request failed | agent=%s | status=%s | body=%s",
            agent,
            resp.status_code,
            resp.text[:500],
        )
        resp.raise_for_status()

    j = resp.json()
    expanded_text = j["choices"][0]["message"]["content"].strip()

    # Извлекаем usage
    finish_reason = j.get("choices", [{}])[0].get("finish_reason", "unknown")
    tokens_input, tokens_output, tokens_total = _extract_usage(j)

    usage_dict = {
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "tokens_total": tokens_total,
        "finish_reason": finish_reason,
        "latency_ms": latency_ms,
    }

    logger.info(
        "Expander usage | agent=%s | tokens_out=%d | text_len=%d",
        agent,
        tokens_output,
        len(expanded_text),
    )

    return expanded_text, usage_dict


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def _extract_usage(response_json: dict) -> Tuple[int, int, int]:
    """
    Извлекает информацию об использованных токенах из ответа GigaChat API.
    
    Args:
        response_json: JSON ответ от API
        
    Returns:
        Tuple[int, int, int]: (prompt_tokens, completion_tokens, total_tokens)
    """
    usage = response_json.get("usage", {})
    return (
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        usage.get("total_tokens", 0),
    )


def create_debug_metadata(
    agent: str,
    compressed_input: Optional[dict] = None,
    compressed_output: Optional[dict] = None,
    latency_ms: float = 0.0,
    tokens_input: int = 0,
    tokens_output: int = 0,
    finish_reason: Optional[str] = None,
) -> DebugMetadata:
    """
    Создаёт объект отладки для агента.
    
    Используется при debug=True в API запросах.
    
    Args:
        agent: имя агента
        compressed_input: сжатые входные данные
        compressed_output: сжатые выходные данные
        latency_ms: время ответа в миллисекундах
        tokens_input: input tokens
        tokens_output: output tokens
        finish_reason: причина завершения (stop, max_tokens и т.д.)
        
    Returns:
        DebugMetadata: объект с информацией об отладке
    """
    return DebugMetadata(
        agent=agent,
        compressed_input=compressed_input,
        compressed_output=compressed_output,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tokens_total=tokens_input + tokens_output,
        latency_ms=latency_ms,
        model=GIGA_MODEL,
        finish_reason=finish_reason,
        timestamp=datetime.now(timezone.utc).isoformat() + "Z",
    )


__all__ = [
    "get_gigachat_token",
    "ask_gigachat",
    "expand_agent_output",
    "create_debug_metadata",
]
