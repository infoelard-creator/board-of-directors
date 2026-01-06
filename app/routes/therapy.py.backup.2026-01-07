"""
Эндпоинт для диалога с Терапевтом.
/api/therapy — главный эндпоинт для сессий терапии.
"""

import json
import uuid
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Depends
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.logger import logger
from app.core.config import RATE_LIMIT_BOARD_CHAT
from app.schemas import ChatRequest
from app.llm import ask_gigachat
from app.services.prompts import AGENT_PARAMS, THERAPY_SYSTEM_PROMPT
from db import (
    SessionLocal,
    get_db,
    TherapySession,
    TherapyMessage,
    TherapyKeyInsight,
    TherapyHypothesis,
    User,
)
from auth import verify_token

# Лимитер для rate limiting
limiter = Limiter(key_func=get_remote_address)

# Создаём router для therapy endpoints
router = APIRouter(prefix="/api", tags=["therapy"])


# ===== SCHEMAS =====

from pydantic import BaseModel

class TherapyKeyInsightSchema(BaseModel):
    """Ключевое знание для ответа."""
    id: str
    insight_summary: str
    confidence: int
    importance: int


class TherapyHypothesisSchema(BaseModel):
    """Гипотеза для ответа."""
    id: str
    hypothesis_text: str
    confidence: int
    is_ready_for_board: bool


class TherapyRequest(BaseModel):
    """Запрос к Терапевту."""
    session_id: Optional[str] = None  # None если новая сессия
    message: str


class TherapyResponse(BaseModel):
    """Ответ от Терапевта."""
    session_id: str
    therapist_message: str
    key_insights: List[TherapyKeyInsightSchema]
    hypotheses: List[TherapyHypothesisSchema]
    ready_for_board: bool


# ===== HELPER FUNCTIONS =====

def get_therapy_context(session: TherapySession, max_recent_messages: int = 10) -> str:
    """
    Собирает контекст для Терапевта.
    
    Состав:
    1. Исходная проблема
    2. Ключевые знания (отсортированы по importance)
    3. Удаленные знания (для анализа Терапевтом)
    4. Последние N сообщений из истории
    """
    parts = []
    
    # 1. Исходная проблема
    parts.append("ИСХОДНАЯ ПРОБЛЕМА:")
    parts.append(session.initial_problem)
    
    # 2. Ключевые знания (активные)
    active_insights = [i for i in session.key_insights if not i.is_deleted_by_user]
    if active_insights:
        parts.append("\nКЛЮЧЕВЫЕ ЗНАНИЯ (отсортированы по важности):")
        for insight in sorted(active_insights, key=lambda x: x.importance, reverse=True):
            parts.append(f"- {insight.insight_summary} (уверенность: {insight.confidence}%)")
    
    # 3. Удаленные знания (для анализа Терапевтом)
    deleted_insights = [i for i in session.key_insights if i.is_deleted_by_user]
    if deleted_insights:
        parts.append("\nРАНЕЕ УПОМЯНУТЫЕ (но удаленные пользователем):")
        for insight in deleted_insights:
            parts.append(f"- {insight.insight_summary}")
    
    # 4. Последние N сообщений
    recent_messages = sorted(session.messages, key=lambda x: x.created_at)[-max_recent_messages:]
    if recent_messages:
        parts.append(f"\nПОСЛЕДНИЕ {len(recent_messages)} СООБЩЕНИЙ:")
        for msg in recent_messages:
            role = "Пользователь" if msg.role == "user" else "Терапевт"
            parts.append(f"{role}: {msg.content}")
    
    return "\n".join(parts)


# ===== API ENDPOINTS =====

@router.post("/therapy", response_model=TherapyResponse)
@limiter.limit(RATE_LIMIT_BOARD_CHAT)
async def therapy_chat(
    req: TherapyRequest,
    request: Request,
    user_id: str = Depends(verify_token),
    db = Depends(get_db),
) -> TherapyResponse:
    """
    Основной эндпоинт для диалога с Терапевтом.
    
    Flow:
    1. Если session_id = None → создаём новую сессию
    2. Сохраняем сообщение пользователя в БД
    3. Собираем контекст для Терапевта
    4. Вызываем Терапевта (спрашиваем пользователя)
    5. Генерируем гипотезы отдельным запросом
    6. Возвращаем ответ с обновленными insights и hypotheses
    """
    
    user_msg = req.message
    session_id = req.session_id
    
    logger.info(
        "Incoming /api/therapy | session_id=%s | user_msg=%s | user=%s",
        session_id,
        user_msg[:50],
        user_id,
    )
    
    # ===== ЭТАП 1: СОЗДАНИЕ ИЛИ ЗАГРУЗКА СЕССИИ =====
    
    if not session_id:
        # Новая сессия
        session_id = str(uuid.uuid4())
        session = TherapySession(
            id=session_id,
            user_id=user_id,
            initial_problem=user_msg,
            status="ongoing",
        )
        db.add(session)
        db.commit()
        db.refresh(session)
        
        logger.info("Created new therapy session: %s", session_id)
    else:
        # Загружаем существующую
        session = db.query(TherapySession).filter(
            TherapySession.id == session_id,
            TherapySession.user_id == user_id,
        ).first()
        
        if not session:
            logger.error("Session not found: %s for user %s", session_id, user_id)
            raise ValueError(f"Сессия {session_id} не найдена")
    
    # ===== ЭТАП 2: СОХРАНИТЬ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ =====
    
    user_message = TherapyMessage(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="user",
        content=user_msg,
    )
    db.add(user_message)
    db.commit()
    
    # ===== ЭТАП 3: СОБРАТЬ КОНТЕКСТ И ВЫЗВАТЬ ТЕРАПЕВТА =====
    
    context = get_therapy_context(session)
    therapy_input = f"{context}\n\nТекущий ответ пользователя: {user_msg}"
    
    # Вызываем Терапевта (он спрашивает пользователя)
    therapist_raw_response, usage = ask_gigachat(
        "therapy",
        therapy_input,
        track_usage=False,
    )
    
    logger.info(
        "Therapist responded | session_id=%s | response=%s",
        session_id,
        therapist_raw_response[:100],
    )
    
    # Парсим JSON ответ от Терапевта
    try:
        therapist_response = json.loads(therapist_raw_response)
        therapist_message = therapist_response.get("question", "")
        
        # Экстрактим ключевое знание из ответа пользователя (если есть)
        if "key_insight" in therapist_response:
            insight = TherapyKeyInsight(
                id=str(uuid.uuid4()),
                session_id=session_id,
                question=therapist_response.get("question_asked", ""),
                answer=user_msg,
                insight_summary=therapist_response.get("key_insight", ""),
                confidence=therapist_response.get("insight_confidence", 80),
                importance=therapist_response.get("insight_importance", 80),
                display_order=len(session.key_insights),
            )
            db.add(insight)
            db.commit()
            
            logger.info("Saved key insight: %s", insight.insight_summary)
    
    except json.JSONDecodeError as e:
        logger.warning("Therapist returned non-JSON: %s", e)
        therapist_message = therapist_raw_response
        therapist_response = {}
    
    # ===== ЭТАП 4: СОХРАНИТЬ ОТВЕТ ТЕРАПЕВТА =====
    
    therapist_message_obj = TherapyMessage(
        id=str(uuid.uuid4()),
        session_id=session_id,
        role="therapist",
        content=therapist_message,
    )
    db.add(therapist_message_obj)
    db.commit()
    
    # ===== ЭТАП 5: ГЕНЕРИРОВАТЬ ГИПОТЕЗЫ (ВАРИАНТ B) =====
    
    # Вызываем Терапевта еще раз для генерации гипотез
    hypothesis_input = f"""{context}

Текущий ответ пользователя: {user_msg}

На основе всей информации выше, сформулируй 3-5 гипотез о том, какую проблему хочет решить пользователь.
Для каждой гипотезы указать:
1. hypothesis_text — понятное описание (2-3 предложения)
2. confidence — 0-100, насколько уверен
3. json_format — JSON для отправки на Board (заполнить позже)

Выдай JSON список."""
    
    hypotheses_raw, _ = ask_gigachat("therapy_hypothesis_generator", hypothesis_input)
    
    try:
        hypotheses_data = json.loads(hypotheses_raw)
        for idx, hyp_data in enumerate(hypotheses_data.get("hypotheses", [])):
            hypothesis = TherapyHypothesis(
                id=str(uuid.uuid4()),
                session_id=session_id,
                hypothesis_text=hyp_data.get("hypothesis_text", ""),
                confidence=hyp_data.get("confidence", 50),
                is_active=True,
            )
            db.add(hypothesis)
        db.commit()
        
        logger.info("Generated %d hypotheses for session %s", len(hypotheses_data.get("hypotheses", [])), session_id)
    
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse hypotheses JSON: %s", e)
    
    # ===== ЭТАП 6: СОБРАТЬ ОТВЕТ =====
    
    # Перезагружаем сессию чтобы получить обновленные insights и hypotheses
    db.refresh(session)
    
    active_insights = [
        TherapyKeyInsightSchema(
            id=i.id,
            insight_summary=i.insight_summary,
            confidence=i.confidence,
            importance=i.importance,
        )
        for i in session.key_insights
        if not i.is_deleted_by_user
    ]
    
    active_hypotheses = [
        h for h in session.hypotheses
        if h.is_active and not h.is_selected_by_user
    ]
    
    hypotheses_for_response = [
        TherapyHypothesisSchema(
            id=h.id,
            hypothesis_text=h.hypothesis_text,
            confidence=h.confidence,
            is_ready_for_board=h.confidence >= 85,
        )
        for h in active_hypotheses
    ]
    
    # Проверяем есть ли гипотезы готовые к Board
    ready_for_board = any(h.is_ready_for_board for h in hypotheses_for_response)
    
    response = TherapyResponse(
        session_id=session_id,
        therapist_message=therapist_message,
        key_insights=active_insights,
        hypotheses=hypotheses_for_response,
        ready_for_board=ready_for_board,
    )
    
    logger.info(
        "Therapy response | session_id=%s | ready_for_board=%s | insights=%d | hypotheses=%d",
        session_id,
        ready_for_board,
        len(active_insights),
        len(hypotheses_for_response),
    )
    
    return response
