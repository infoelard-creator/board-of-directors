"""
Эндпойнты для работы с отдельными агентами.
Одиночные агенты и пересчёт саммари.
"""

from typing import List
from fastapi import APIRouter, Request, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.logger import logger
from app.core.config import RATE_LIMIT_SINGLE_AGENT, RATE_LIMIT_SUMMARY
from app.schemas import (
    SingleAgentRequest,
    SummaryRequest,
    AgentReplyV2,
)
from app.llm import (
    ask_gigachat,
    expand_agent_output,
    compress_user_message,
    compress_history,
    create_debug_metadata,
)
from app.services.prompts import AGENT_SYSTEM_PROMPTS
from auth import verify_token

# Лимитер для rate limiting
limiter = Limiter(key_func=get_remote_address)

# Создаём router для группировки agent endpoints
router = APIRouter(prefix="/api", tags=["agent"])


@router.post("/agent", response_model=AgentReplyV2)
@limiter.limit(RATE_LIMIT_SINGLE_AGENT)
async def single_agent(
    req: SingleAgentRequest,
    request: Request,
    user_id: str = Depends(verify_token),
) -> AgentReplyV2:
    """
    Запрос к одному агенту с опциональной отладкой.
    
    Args:
        req: SingleAgentRequest с agent, message, history
        request: FastAPI Request (для rate limiter)
        user_id: текущий пользователь (из JWT)
        
    Returns:
        AgentReplyV2: ответ агента с опциональной отладкой
    """
    logger.info(
        "Incoming /api/agent: agent=%s | message=%s | user=%s | debug=%s",
        req.agent,
        (req.message or "")[:50] if req.message else "None",
        user_id,
        req.debug,
    )

    # Проверяем, существует ли такой агент
    if req.agent not in AGENT_SYSTEM_PROMPTS:
        return AgentReplyV2(agent=req.agent, text=f"Неизвестный агент: {req.agent}")

    # Собираем контекст для агента
    parts: List[str] = []

    if req.message:
        # Сжимаем сообщение пользователя
        compressed_msg = compress_user_message(req.message, user_id=user_id)
        logger.info(
            "Compressed single message | intent=%s | domain=%s",
            compressed_msg.intent,
            compressed_msg.domain,
        )

        parts.extend([
            "СЖАТЫЙ ЗАПРОС (JSON):",
            str(compressed_msg.dict()),  # ← Должно быть JSON, но для простоты str()
        ])

    # Добавляем выдержку из истории
    compressed = compress_history(req.history, max_items=5)
    if compressed:
        parts.append("\nВЫДЕЖКА ИЗ ИСТОРИИ (последние 5):")
        parts.append(compressed)

    # Если ничего нет — даём агенту общее задание
    if not parts:
        parts.append(
            "Проанализируй ситуацию и предложи конкретную идею/замечание от своей роли."
        )

    full_content = "\n".join(parts)

    try:
        # Получаем ответ от агента
        raw_response, agent_usage = ask_gigachat(req.agent, full_content, track_usage=req.debug)

        # Парсим JSON ответ
        import json
        try:
            compressed_response = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Agent %s returned non-JSON: %s", req.agent, raw_response[:100])
            compressed_response = {
                "verdict": "NO-DATA",
                "confidence": 0,
                "raw_response": raw_response[:500]
            }

        # Разворачиваем в читаемый текст
        expanded_text, expander_usage = expand_agent_output(req.agent, compressed_response, track_usage=req.debug)

        # Собираем ответ
        reply = AgentReplyV2(
            agent=req.agent,
            text=expanded_text,
        )

        # Добавляем отладку если нужна
        if req.debug:
            reply.compressed = compressed_response
            reply.meta = create_debug_metadata(
                agent=req.agent,
                compressed_output=compressed_response,
                latency_ms=agent_usage.get("latency_ms", 0.0) + expander_usage.get("latency_ms", 0.0),
                tokens_input=agent_usage.get("tokens_input", 0) + expander_usage.get("tokens_input", 0),
                tokens_output=agent_usage.get("tokens_output", 0) + expander_usage.get("tokens_output", 0),
                finish_reason=agent_usage.get("finish_reason", "unknown"),
            )

        logger.info("Outgoing /api/agent | agent=%s | user=%s", req.agent, user_id)
        return reply

    except Exception as e:
        logger.exception("Error in /api/agent | agent=%s | user=%s", req.agent, user_id)
        return AgentReplyV2(
            agent=req.agent,
            text=f"Ошибка при обращении к GigaChat для агента {req.agent}: {e}",
        )


@router.post("/summary", response_model=AgentReplyV2)
@limiter.limit(RATE_LIMIT_SUMMARY)
async def recalc_summary(
    req: SummaryRequest,
    request: Request,
    user_id: str = Depends(verify_token),
) -> AgentReplyV2:
    """
    Пересчёт итогов на основе истории.
    
    Args:
        req: SummaryRequest с history
        request: FastAPI Request (для rate limiter)
        user_id: текущий пользователь (из JWT)
        
    Returns:
        AgentReplyV2: саммари с опциональной отладкой
    """
    logger.info(
        "Incoming /api/summary | history_len=%s | user=%s | debug=%s",
        len(req.history) if req.history else 0,
        user_id,
        req.debug,
    )

    # Сжимаем историю
    compressed = compress_history(req.history, max_items=5)

    if not compressed:
        return AgentReplyV2(
            agent="summary",
            text="Недостаточно истории для пересчёта итогов. Сначала проведите обсуждение."
        )

    # Подготавливаем input для саммари агента
    summary_input = (
        "Вот выдержка из истории обсуждения совета директоров "
        "(последние 5 сообщений):\n\n"
        f"{compressed}\n\n"
        "Подведи обновлённые итоги по инструкции из system-подсказки."
    )

    try:
        # Получаем ответ от саммари агента
        raw_response, summary_usage = ask_gigachat("summary", summary_input, track_usage=req.debug)

        # Парсим JSON ответ
        import json
        try:
            compressed_response = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Summary returned non-JSON: %s", raw_response[:100])
            compressed_response = {
                "verdict": "NO-DATA",
                "confidence": 0,
                "raw_response": raw_response[:500]
            }

        # Разворачиваем в читаемый текст
        expanded_text, expander_usage = expand_agent_output("summary", compressed_response, track_usage=req.debug)

        # Собираем ответ
        reply = AgentReplyV2(
            agent="summary",
            text=expanded_text,
        )

        # Добавляем отладку если нужна
        if req.debug:
            reply.compressed = compressed_response
            reply.meta = create_debug_metadata(
                agent="summary",
                compressed_output=compressed_response,
                latency_ms=summary_usage.get("latency_ms", 0.0) + expander_usage.get("latency_ms", 0.0),
                tokens_input=summary_usage.get("tokens_input", 0) + expander_usage.get("tokens_input", 0),
                tokens_output=summary_usage.get("tokens_output", 0) + expander_usage.get("tokens_output", 0),
                finish_reason=summary_usage.get("finish_reason", "unknown"),
            )

        logger.info("Outgoing /api/summary | user=%s", user_id)
        return reply

    except Exception as e:
        logger.exception("Error in /api/summary | user=%s", user_id)
        return AgentReplyV2(
            agent="summary",
            text=f"Ошибка при обращении к GigaChat для пересчёта итогов: {e}",
        )
