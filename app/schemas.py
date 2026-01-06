"""
Pydantic модели (схемы) для всего приложения.
Используются для валидации и документации API.
"""

from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime


# ===== ПАРСИНГ И СЖАТИЕ =====

class ParsedRequest(BaseModel):
    """Структурированный запрос после парсера."""
    original_message: str
    intent: str
    domain: str
    key_points: List[str] = []
    assumptions: List[str] = []
    constraints: List[str] = []
    summary: Optional[str] = None
    confidence: float = 0.85


class CompressedMessage(BaseModel):
    """Сжатое представление сообщения пользователя."""
    intent: str
    domain: str
    idea_summary: Optional[str] = None
    key_points: List[str] = []
    constraints: Optional[Dict] = None
    assumptions: List[str] = []
    key_facts: List[str] = []


# ===== API REQUESTS =====

class ChatRequest(BaseModel):
    """Запрос для эндпойнта /api/board."""
    message: str
    active_agents: Optional[List[str]] = None
    history: Optional[List[str]] = None
    mode: Optional[str] = None
    debug: Optional[bool] = False


class SingleAgentRequest(BaseModel):
    """Запрос для одного агента."""
    agent: str
    message: Optional[str] = None
    history: Optional[List[str]] = None
    debug: Optional[bool] = False


class SummaryRequest(BaseModel):
    """Запрос пересчёта итогов."""
    history: Optional[List[str]] = None
    debug: Optional[bool] = False


class LoginRequest(BaseModel):
    """Запрос логина."""
    user_id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern="^[a-zA-Z0-9_-]+$",
        description="User ID (буквы, цифры, подчёркивание, дефис)"
    )


# ===== AUTHENTICATION (из auth.py) =====

class TokenResponse(BaseModel):
    """Ответ при логине — оба токена."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # в секундах


class AccessTokenResponse(BaseModel):
    """Ответ при обновлении access_token'а."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # в секундах


class RefreshTokenRequest(BaseModel):
    """Request для /api/refresh endpoint'а."""
    refresh_token: str


# ===== DEBUG METADATA =====

class DebugMetadata(BaseModel):
    """Отладочная информация агента."""
    agent: str
    compressed_input: Optional[dict] = None
    compressed_output: Optional[dict] = None
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0
    latency_ms: float = 0.0
    model: str = "GigaChat-2"
    finish_reason: Optional[str] = None
    timestamp: str = ""


# ===== AGENT RESPONSES =====

class AgentReplyV2(BaseModel):
    """Ответ агента с опциональной отладкой."""
    agent: str
    text: str
    compressed: Optional[dict] = None
    meta: Optional[DebugMetadata] = None


class ChatResponseV2(BaseModel):
    """Единая структура ответа."""
    agents: List[AgentReplyV2]
    user_message_compressed: Optional[dict] = None
    debug: bool = False
