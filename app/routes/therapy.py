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
from app.services.prompts import (
    AGENT_PARAMS,
    THERAPY_SYSTEM_PROMPT,
    HYPOTHESIS_GENERATOR_SYSTEM_PROMPT,
    HYPOTHESIS_DEDUPLICATOR_SYSTEM_PROMPT,
)
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
    4. ТЕКУЩИЕ ГИПОТЕЗЫ (отсортированы по confidence)
    5. Последние N сообщений из истории
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
    
    # 4. ТЕКУЩИЕ ГИПОТЕЗЫ - отсортированы по confidence (убывание), топ-10
    active_hypotheses = [h for h in session.hypotheses if h.is_active and not h.is_selected_by_user]
    if active_hypotheses:
        sorted_hypotheses = sorted(active_hypotheses, key=lambda x: x.confidence or 0, reverse=True)
        top_hypotheses = sorted_hypotheses[:10]
        
        parts.append("\nТЕКУЩИЕ ГИПОТЕЗЫ (отсортированы по confidence):")
        for idx, hyp in enumerate(top_hypotheses, 1):
            parts.append(f"{idx}. [{hyp.id[:8]}] {hyp.hypothesis_text} (confidence: {hyp.confidence}%)")
    
    # 5. Последние N сообщений
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
    
    # ===== ЭТАП 5: ГЕНЕРАТОР ГИПОТЕЗ (новые + обновлённые) =====
    
    # Перезагружаем сессию чтобы получить обновлённые данные (инсайты, старые гипотезы)
    db.refresh(session)
    
    # Пересобираем контекст (теперь с новым инсайтом если был)
    context = get_therapy_context(session)
    
    hypothesis_input = f"""{context}

Текущий ответ пользователя: {user_msg}

На основе всей информации выше, проанализируй:
1. Какие текущие гипотезы нужно обновить по confidence?
2. Какие НОВЫЕ гипотезы возникают?

Помни: твоя задача не дублировать, а ОБНОВЛЯТЬ и ГЕНЕРИРОВАТЬ."""
    
    gen_response_raw, _ = ask_gigachat("therapy_hypothesis_generator", hypothesis_input)
    
    logger.info(
        "Generator responded | session_id=%s | response_len=%d",
        session_id,
        len(gen_response_raw),
    )
    
    # Парсим ответ Генератора
    updated_hypotheses = []
    new_hypotheses = []
    try:
        gen_response = json.loads(gen_response_raw)
        updated_hypotheses = gen_response.get("updated_hypotheses", [])
        new_hypotheses = gen_response.get("new_hypotheses", [])
        
        logger.info(
            "Generator parsed | updated=%d | new=%d",
            len(updated_hypotheses),
            len(new_hypotheses),
        )
    except json.JSONDecodeError as e:
        logger.warning("Generator returned non-JSON: %s", e)
    
    # ===== ЭТАП C: ДЕДУПЛИКАТОР (финальный список) =====
    
    dedup_input = f"""ОБНОВЛЁННЫЕ СТАРЫЕ ГИПОТЕЗЫ:
{json.dumps(updated_hypotheses, ensure_ascii=False, indent=2)}

НОВЫЕ ГИПОТЕЗЫ:
{json.dumps(new_hypotheses, ensure_ascii=False, indent=2)}

Выполни дедупликацию и верни финальный список."""
    
    dedup_response_raw, _ = ask_gigachat("therapy_hypothesis_deduplicator", dedup_input)
    
    logger.info(
        "Deduplicator responded | session_id=%s | response_len=%d",
        session_id,
        len(dedup_response_raw),
    )
    
    # Парсим ответ Дедупликатора
    final_hypotheses = []
    try:
        dedup_response = json.loads(dedup_response_raw)
        final_hypotheses = dedup_response.get("hypotheses", [])
        
        logger.info(
            "Deduplicator parsed | final=%d hypotheses",
            len(final_hypotheses),
        )
    except json.JSONDecodeError as e:
        logger.warning("Deduplicator returned non-JSON: %s", e)
    
    # ===== ЭТАП 5B: СОХРАНИТЬ ГИПОТЕЗЫ В БД =====
    
    # Получаем текущие ID гипотез для обновления
    existing_hyp_ids = {h.id for h in session.hypotheses}
    
    for final_hyp in final_hypotheses:
        hyp_id = final_hyp.get("id")
        hyp_text = final_hyp.get("hypothesis_text", "")
        hyp_confidence = final_hyp.get("confidence", 50)
        is_new = final_hyp.get("is_new", False)
        
        if not hyp_text:
            continue
        
        if hyp_id and hyp_id in existing_hyp_ids:
            # Обновляем существующую гипотезу
            hyp_obj = db.query(TherapyHypothesis).filter(
                TherapyHypothesis.id == hyp_id
            ).first()
            if hyp_obj:
                hyp_obj.hypothesis_text = hyp_text
                hyp_obj.confidence = hyp_confidence
                hyp_obj.updated_at = datetime.now(timezone.utc)
                
                logger.info(
                    "Updated hypothesis | id=%s | confidence=%d",
                    hyp_id[:8],
                    hyp_confidence,
                )
        else:
            # Создаём новую гипотезу
            new_hyp = TherapyHypothesis(
                id=str(uuid.uuid4()),
                session_id=session_id,
                hypothesis_text=hyp_text,
                confidence=hyp_confidence,
                is_active=True,
            )
            db.add(new_hyp)
            
            logger.info(
                "Created new hypothesis | confidence=%d",
                hyp_confidence,
            )
    
    db.commit()


    # ===== ЭТАП 6: СОБРАТЬ ОТВЕТ =====
    
    # Перезагружаем сессию чтобы получить обновленные insights и hypotheses
    db.refresh(session)
    
    active_insights = [
        TherapyKeyInsightSchema(
            id=i.id,
            insight_summary=i.insight_summary or "Ключевое знание",  # Дефолт если None
            confidence=i.confidence or 0,  # Дефолт если None
            importance=i.importance or 0,  # Дефолт если None
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


@router.delete("/therapy/insights/{insight_id}")
@limiter.limit(RATE_LIMIT_BOARD_CHAT)
async def delete_therapy_insight(
    insight_id: str,
    request: Request,
    user_id: str = Depends(verify_token),
    db = Depends(get_db),
):
    """
    Удалить инсайт (отметить как удалённый пользователем).
    Это НЕ удаление из БД, а установка флага is_deleted_by_user = True.
    Терапевт будет видеть удалённые инсайты в контексте и понимать что это чувствительные темы.
    """
    
    # Находим инсайт
    insight = db.query(TherapyKeyInsight).filter(
        TherapyKeyInsight.id == insight_id
    ).first()
    
    if not insight:
        logger.warning("Insight not found: %s", insight_id)
        return {"status": "not_found", "message": "Инсайт не найден"}
    
    # Проверяем что инсайт принадлежит сессии текущего пользователя
    session = db.query(TherapySession).filter(
        TherapySession.id == insight.session_id,
        TherapySession.user_id == user_id,
    ).first()
    
    if not session:
        logger.warning(
            "Insight %s doesn't belong to user %s",
            insight_id,
            user_id,
        )
        return {"status": "forbidden", "message": "Доступ запрещён"}
    
    # Отмечаем как удалённый
    insight.is_deleted_by_user = True
    insight.deleted_at = datetime.now(timezone.utc)
    db.commit()
    
    logger.info(
        "Insight marked as deleted | insight_id=%s | session_id=%s",
        insight_id[:8],
        insight.session_id[:8],
    )
    
    return {
        "status": "success",
        "message": "Инсайт удалён",
        "insight_id": insight_id,
    }
