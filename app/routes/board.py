"""
Основной endpoint для совета директоров.
/api/board — главная бизнес-логика приложения.
"""

import json
from typing import List, Optional, Dict
from fastapi import APIRouter, Request, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.logger import logger
from app.core.config import RATE_LIMIT_BOARD_CHAT
from app.schemas import (
    ChatRequest,
    ChatResponseV2,
    AgentReplyV2,
)
from app.llm import (
    ask_gigachat,
    expand_agent_output,
    compress_user_message,
    compress_history,
    create_debug_metadata,
)
from app.services.prompts import AGENT_PARAMS
from auth import verify_token

# Лимитер для rate limiting
limiter = Limiter(key_func=get_remote_address)

# Создаём router для board endpoints
router = APIRouter(prefix="/api", tags=["board"])

# Порядок агентов при выводе
AGENT_ORDER = ["ceo", "cfo", "cpo", "marketing", "skeptic"]


@router.post("/board", response_model=ChatResponseV2)
@limiter.limit(RATE_LIMIT_BOARD_CHAT)
async def board_chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(verify_token),
) -> ChatResponseV2:
    """
    Оптимизированный endpoint совета директоров.
    
    流程:
    1. Сжимает исходное сообщение пользователя
    2. Вызывает всех активных агентов по очереди
    3. Каждый агент видит мнения предыдущих
    4. После всех агентов — пересчёт саммари
    5. Возвращает все ответы + опциональная отладка
    
    Args:
        req: ChatRequest с message, active_agents, history, mode, debug
        request: FastAPI Request (для rate limiter)
        user_id: текущий пользователь (из JWT)
        
    Returns:
        ChatResponseV2: ответы всех агентов + опциональная отладка
    """
    user_msg = req.message
    mode = req.mode or "initial"
    debug = req.debug or False

    logger.info(
        "Incoming /api/board message: %s | active_agents=%s | mode=%s | debug=%s | user=%s",
        user_msg[:50],
        req.active_agents,
        mode,
        debug,
        user_id,
    )

    # Определяем порядок агентов
    order = AGENT_ORDER
    active = req.active_agents if req.active_agents is not None else order
    active_ordered = [a for a in order if a in active]

    # Сжимаем исходное сообщение пользователя
    compressed_user_msg = compress_user_message(user_msg, user_id=user_id)
    logger.info(
        "Compressed user message | intent=%s | domain=%s | idea_summary=%s",
        compressed_user_msg.intent,
        compressed_user_msg.domain,
        compressed_user_msg.idea_summary,
    )

    replies: List[AgentReplyV2] = []
    ctx: Dict[str, dict] = {}  # Контекст для каждого агента (его мнение + usage)

    try:
        # ===== ЦИКЛ ПО АГЕНТАМ =====
        for agent in active_ordered:
            logger.info("Processing agent: %s", agent)

            # Собираем контекст для этого агента
            parts: List[str] = [
                "СЖАТЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ (JSON):",
                json.dumps(compressed_user_msg.dict(), ensure_ascii=False, indent=2),
            ]

            # Если есть мнения других агентов — добавляем их
            if ctx:
                parts.append("\nСЖАТЫЕ МНЕНИЯ ДРУГИХ ЧЛЕНОВ СОВЕТА (JSON):")
                for prev_agent in order:
                    if prev_agent in ctx:
                        parts.append(f"{prev_agent}:")
                        parts.append(json.dumps(ctx[prev_agent]["compressed"], ensure_ascii=False, indent=2))

            # Добавляем выдержку из истории (последние 5 сообщений)
            compressed = compress_history(req.history, max_items=5)
            if compressed:
                parts.append("\nВЫДЕЖКА ИЗ ИСТОРИИ (последние 5 сообщений):")
                parts.append(compressed)

            agent_input = "\n".join(parts)

            # Получаем raw ответ от агента (сжатый JSON)
            raw_response, agent_usage = ask_gigachat(agent, agent_input, track_usage=debug)

            # Парсим JSON из ответа
            try:
                compressed_response = json.loads(raw_response)
                
                # Валидируем наличие ключевых полей
                if "verdict" not in compressed_response or "confidence" not in compressed_response:
                    logger.warning(
                        "Agent %s returned JSON but missing critical fields | keys=%s",
                        agent,
                        list(compressed_response.keys())
                    )
                    compressed_response = {
                        "verdict": "INCOMPLETE",
                        "confidence": 0,
                        "raw_response": raw_response,
                        **compressed_response
                    }
                else:
                    logger.info(
                        "Agent %s returned valid JSON | verdict=%s | confidence=%d",
                        agent,
                        compressed_response.get("verdict", "N/A"),
                        compressed_response.get("confidence", 0),
                    )
            except json.JSONDecodeError as e:
                logger.warning(
                    "Agent %s returned non-JSON response: %s | error=%s",
                    agent,
                    raw_response[:100],
                    str(e)
                )
                compressed_response = {
                    "verdict": "NO-DATA",
                    "confidence": 0,
                    "raw_response": raw_response[:500]
                }

            # Сохраняем мнение агента в контекст для следующих
            ctx[agent] = {"compressed": compressed_response, "usage": agent_usage}

            # Разворачиваем JSON в читаемый текст
            expanded_text, expander_usage = expand_agent_output(agent, compressed_response, track_usage=debug)

            # Собираем ответ агента
            reply = AgentReplyV2(
                agent=agent,
                text=expanded_text,
            )

            # Добавляем отладку если нужна
            if debug:
                reply.compressed = compressed_response
                reply.meta = create_debug_metadata(
                    agent=agent,
                    compressed_input={"user_msg": user_msg[:100], "intent": compressed_user_msg.intent},
                    compressed_output=compressed_response,
                    latency_ms=agent_usage.get("latency_ms", 0.0) + expander_usage.get("latency_ms", 0.0),
                    tokens_input=agent_usage.get("tokens_input", 0) + expander_usage.get("tokens_input", 0),
                    tokens_output=agent_usage.get("tokens_output", 0) + expander_usage.get("tokens_output", 0),
                    finish_reason=agent_usage.get("finish_reason", "unknown"),
                )

            replies.append(reply)

        # ===== САММАРИ ПОСЛЕ ВСЕХ АГЕНТОВ =====
        if mode == "initial":
            logger.info("Processing summary agent")

            # Собираем контекст для саммари
            summary_parts: List[str] = [
                "СЖАТЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ (JSON):",
                json.dumps(compressed_user_msg.dict(), ensure_ascii=False, indent=2),
                "",
                "СЖАТЫЕ МНЕНИЯ СОВЕТА (JSON):",
            ]

            for agent in active_ordered:
                if agent in ctx:
                    summary_parts.append(f"{agent}:")
                    summary_parts.append(json.dumps(ctx[agent]["compressed"], ensure_ascii=False, indent=2))

            summary_input = "\n".join(summary_parts)

            # Получаем ответ от саммари агента
            raw_summary, summary_usage = ask_gigachat("summary", summary_input, track_usage=debug)

            # Парсим JSON
            try:
                compressed_summary = json.loads(raw_summary)
                if "verdict" not in compressed_summary or "confidence" not in compressed_summary:
                    logger.warning(
                        "Summary returned JSON but missing critical fields | keys=%s",
                        list(compressed_summary.keys())
                    )
                    compressed_summary = {
                        "verdict": "INCOMPLETE",
                        "confidence": 0,
                        **compressed_summary
                    }
            except json.JSONDecodeError:
                logger.warning("Summary agent returned non-JSON: %s", raw_summary[:100])
                compressed_summary = {
                    "verdict": "NO-DATA",
                    "confidence": 0,
                    "raw_response": raw_summary[:500]
                }

            # Разворачиваем саммари
            expanded_summary, expander_summary_usage = expand_agent_output("summary", compressed_summary, track_usage=debug)

            # Собираем ответ саммари
            reply = AgentReplyV2(
                agent="summary",
                text=expanded_summary,
            )

            if debug:
                reply.compressed = compressed_summary
                reply.meta = create_debug_metadata(
                    agent="summary",
                    compressed_output=compressed_summary,
                    latency_ms=summary_usage.get("latency_ms", 0.0) + expander_summary_usage.get("latency_ms", 0.0),
                    tokens_input=summary_usage.get("tokens_input", 0) + expander_summary_usage.get("tokens_input", 0),
                    tokens_output=summary_usage.get("tokens_output", 0) + expander_summary_usage.get("tokens_output", 0),
                    finish_reason=summary_usage.get("finish_reason", "unknown"),
                )

            replies.append(reply)

    except Exception as e:
        logger.exception("Error while calling GigaChat board chain | user=%s", user_id)
        replies.append(
            AgentReplyV2(
                agent="error",
                text=f"Ошибка при обращении к GigaChat: {e}",
            )
        )

    logger.info(
        "Outgoing /api/board | agents=%s | reply_count=%d | debug=%s",
        active_ordered,
        len(replies),
        debug,
    )

    return ChatResponseV2(
        agents=replies,
        user_message_compressed=compressed_user_msg.dict() if debug else None,
        debug=debug,
    )
