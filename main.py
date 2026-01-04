import os
import uuid
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Union
import hashlib
import json
import requests
from threading import Lock  
from fastapi import FastAPI, Request, Depends
from auth import create_access_token, create_token_pair, verify_token, verify_refresh_token, TokenResponse, AccessTokenResponse, RefreshTokenRequest
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import logging
from logging.handlers import RotatingFileHandler
from db import init_db, get_db, create_user_if_not_exists, User
from sqlalchemy.orm import Session
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Импорт промптов и параметров из отдельного модуля
from app.services.prompts import (
    AGENT_PARAMS,
    COMPRESSOR_SYSTEM_PROMPT,
    EXPANDER_SYSTEM_PROMPT,
    AGENT_SYSTEM_PROMPTS,
    PARSER_SYSTEM_PROMPT,
)

# ===== ЛОГИРОВАНИЕ =====

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("gigachat")
logger.setLevel(logging.INFO)

log_path = os.path.join(LOG_DIR, "gigachat.log")
handler = RotatingFileHandler(
    log_path,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
handler.setFormatter(formatter)
logger.addHandler(handler)

# ===== НАСТРОЙКИ GIGACHAT =====

GIGA_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGA_API_BASE = "https://gigachat.devices.sberbank.ru"
GIGA_SCOPE = "GIGACHAT_API_PERS"

GIGA_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")

if not GIGA_AUTH_KEY:
    raise RuntimeError("Не задана переменная окружения GIGACHAT_AUTH_KEY")

_access_token: Optional[str] = None
_access_exp: Optional[datetime] = None

# ===== КЭШ ПАРСЕРА И СЖАТЫХ СООБЩЕНИЙ =====
_parsed_cache: dict[str, "ParsedRequest"] = {}
_compressed_cache: dict[str, dict] = {}
_cache_lock = Lock()  


def get_cache_key(user_id: str, message: str) -> str:
    """Генерирует ключ кэша на основе user_id и сообщения."""
    msg_hash = hashlib.md5(message.encode()).hexdigest()[:8]
    return f"{user_id}:{msg_hash}"


def get_cached_parse(user_id: str, message: str) -> Optional["ParsedRequest"]:
    """Получает кэшированный парс запроса."""
    with _cache_lock:
        key = get_cache_key(user_id, message)
        cached = _parsed_cache.get(key)
        if cached:
            logger.info("Parser cache hit | user=%s | message=%s", user_id, message[:50])
        return cached


def cache_parse(user_id: str, message: str, parsed: "ParsedRequest") -> None:
    """Кэширует парс запроса."""
    with _cache_lock:
        key = get_cache_key(user_id, message)
        _parsed_cache[key] = parsed
        if len(_parsed_cache) > 1000:
            keys_to_delete = list(_parsed_cache.keys())[:-500]
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
        if len(_compressed_cache) > 1000:
            keys_to_delete = list(_compressed_cache.keys())[:-500]
            for k in keys_to_delete:
                del _compressed_cache[k]
            logger.info("Compressed cache cleaned | remaining=%d", len(_compressed_cache))

_token_lock = Lock()

def get_gigachat_token() -> str:
    """Получает или обновляет JWT токен доступа к GigaChat API."""
    global _access_token, _access_exp

    with _token_lock:
        if _access_token and _access_exp and datetime.now(timezone.utc) < _access_exp:
            return _access_token

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {GIGA_AUTH_KEY}",
        }
        data = {"scope": GIGA_SCOPE}

        logger.info(
            "Auth request -> %s | headers=%s | data=%s",
            GIGA_AUTH_URL,
            {k: (v if k != "Authorization" else "***hidden***") for k, v in headers.items()},
            data,
        )

        resp = requests.post(GIGA_AUTH_URL, headers=headers, data=data, timeout=10, verify=False)

        logger.info(
            "Auth response <- %s | status=%s | body=%s",
            GIGA_AUTH_URL,
            resp.status_code,
            resp.text,
        )

        resp.raise_for_status()
        j = resp.json()
        _access_token = j["access_token"]
        _access_exp = datetime.now(timezone.utc) + timedelta(minutes=25)

    return _access_token


# ===== ОПТИМИЗИРОВАННЫЕ ПАРАМЕТРЫ И ПРОМПТЫ =====


# ===== ПРОМПТЫ СЖИМАТЕЛЯ И РАЗЖИМАТЕЛЯ =====


# ===== ПРОМПТЫ АГЕНТОВ В НОВОМ СЖАТОМ ФОРМАТЕ =====

# ===== ПАРСЕР ИСХОДНОГО ЗАПРОСА =====

# ===== PYDANTIC МОДЕЛИ =====

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


# ✅ НОВЫЕ МОДЕЛИ ДЛЯ DEBUG

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


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

def extract_usage_from_response(response_json: dict) -> tuple:
    """Извлекает usage из ответа GigaChat API."""
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
    """Создаёт объект отладки для агента."""
    return DebugMetadata(
        agent=agent,
        compressed_input=compressed_input,
        compressed_output=compressed_output,
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        tokens_total=tokens_input + tokens_output,
        latency_ms=latency_ms,
        model="GigaChat-2",
        finish_reason=finish_reason,
        timestamp=datetime.now(timezone.utc).isoformat() + "Z",
    )


def parse_user_request(user_msg: str, user_id: str = "anonymous") -> ParsedRequest:
    """Парсит исходный запрос пользователя в структурированную форму."""
    cached = get_cached_parse(user_id, user_msg)
    if cached:
        return cached

    token = get_gigachat_token()

    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": PARSER_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "temperature": 0.3,
        "max_tokens": 300,
        "top_p": 0.85,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    url = f"{GIGA_API_BASE}/api/v1/chat/completions"

    logger.info(
        "Parser request -> %s | message=%s | user=%s",
        url,
        user_msg[:50],
        user_id,
    )

    resp = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)
    resp.raise_for_status()

    j = resp.json()
    parser_output = j["choices"][0]["message"]["content"].strip()

    logger.info(
        "Parser response <- %s | output=%s",
        url,
        parser_output[:150],
    )

    try:
        parsed_json = json.loads(parser_output)
    except json.JSONDecodeError:
        logger.warning("Parser output is not valid JSON: %s", parser_output)
        parsed_json = {
            "intent": "other",
            "domain": "strategy",
            "key_points": [user_msg[:200]],
            "assumptions": [],
            "constraints": [],
            "summary": user_msg[:200],
        }

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

    cache_parse(user_id, user_msg, parsed)
    return parsed


def compress_user_message(user_msg: str, user_id: str = "anonymous") -> CompressedMessage:
    """Сжимает сообщение пользователя в структурированную выжимку (JSON)."""
    cached = get_cached_compressed(user_id, user_msg)
    if cached:
        logger.info("Compressed message cache hit | user=%s | message=%s", user_id, user_msg[:50])
        return CompressedMessage(**cached)

    token = get_gigachat_token()

    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": COMPRESSOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        "temperature": AGENT_PARAMS["compressor"]["temperature"],
        "max_tokens": AGENT_PARAMS["compressor"]["max_tokens"],
        "top_p": AGENT_PARAMS["compressor"]["top_p"],
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    url = f"{GIGA_API_BASE}/api/v1/chat/completions"

    logger.info(
        "Compressor request -> %s | message=%s | user=%s",
        url,
        user_msg[:50],
        user_id,
    )

    resp = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)
    resp.raise_for_status()

    j = resp.json()
    compressor_output = j["choices"][0]["message"]["content"].strip()

    logger.info(
        "Compressor response <- %s | output=%s",
        url,
        compressor_output[:200],
    )

    try:
        compressed_json = json.loads(compressor_output)
        
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
        compressed_json = {
            "intent": "other",
            "domain": "strategy",
            "idea_summary": user_msg[:100],
            "key_points": [user_msg[:200]],
            "constraints": None,
            "assumptions": [],
            "key_facts": []
        }

    compressed = CompressedMessage(**compressed_json)
    cache_compressed(user_id, user_msg, compressed.dict())
    return compressed


def ask_gigachat(
    agent: str,
    user_msg: str,  # ← Вернули как было
    track_usage: bool = False,
) -> tuple:
    """
    Запрос к GigaChat.
    
    NOTE: user_msg должен УЖЕ СОДЕРЖАТЬ сжатый контекст (JSON из других частей).
    Функция не переделывает input — использует его as-is для LLM.
    
    Возвращает: (ответ_текст, usage_dict)
    """
    token = get_gigachat_token()
    system_prompt = AGENT_SYSTEM_PROMPTS[agent]
    params = AGENT_PARAMS[agent]

    agent_input = user_msg  # ← Ясное присваивание

    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": agent_input},  # ✅ Теперь определена!
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

    resp = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)

    latency_ms = (time.time() - start_time) * 1000

    logger.info(
        "Chat response <- %s | agent=%s | status=%s | latency=%.0fms",
        url,
        agent,
        resp.status_code,
        latency_ms,
    )

    resp.raise_for_status()
    j = resp.json()
    
    finish_reason = j.get("choices", [{}])[0].get("finish_reason", "unknown")
    tokens_input, tokens_output, tokens_total = extract_usage_from_response(j)
    
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
            "Usage | agent=%s | tokens_in=%d | tokens_out=%d | finish_reason=%s",
            agent,
            tokens_input,
            tokens_output,
            finish_reason,
        )
    
    return response_text, usage_dict


def expand_agent_output(
    agent: str,
    compressed_output: dict,
    track_usage: bool = False,
) -> tuple:
    """Разворачивает сжатый JSON-ответ агента в читаемый текст."""
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

    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": EXPANDER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Роль агента: {agent_role}\n\nВот сжатый ответ (JSON), разверни в читаемый текст:\n\n{json.dumps(compressed_output, ensure_ascii=False, indent=2)}"
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

    resp = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)

    latency_ms = (time.time() - start_time) * 1000

    resp.raise_for_status()

    j = resp.json()
    expanded_text = j["choices"][0]["message"]["content"].strip()
    
    finish_reason = j.get("choices", [{}])[0].get("finish_reason", "unknown")
    tokens_input, tokens_output, tokens_total = extract_usage_from_response(j)
    
    usage_dict = {
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "tokens_total": tokens_total,
        "finish_reason": finish_reason,
        "latency_ms": latency_ms,
    }

    logger.info(
        "Expander response <- %s | agent=%s | text_len=%d | latency=%.0fms",
        url,
        agent,
        len(expanded_text),
        latency_ms,
    )

    return expanded_text, usage_dict


def compress_history(history: Optional[List[str]], max_items: int = 15) -> str:
    """Сжимает историю до последних N сообщений для экономии токенов."""
    if not history:
        return ""
    recent = history[-max_items:]
    return "\n".join(recent)


# ===== FASTAPI ПРИЛОЖЕНИЕ =====

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()


@app.on_event("startup")
def on_startup():
    """Инициализация при запуске приложения."""
    init_db()


origins = [
    "http://45.151.31.180:8080",
    "http://localhost:8080",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["Content-Type", "Authorization"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ===== ENDPOINTS =====

@app.post("/api/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """Логин: принимает user_id, создаёт пользователя, возвращает пару токенов."""
    create_user_if_not_exists(db, body.user_id)
    token_pair = create_token_pair(body.user_id)
    logger.info(f"User {body.user_id} logged in, issued token pair")
    return token_pair



@app.post("/api/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(body: RefreshTokenRequest):
    """
    Обновление access_token используя refresh_token.
    Вызывается клиентом когда access_token истекает.
    """
    # Проверяем refresh_token
    user_id = verify_refresh_token(body.refresh_token)
    
    # Выдаем новый access_token
    new_access_token = create_access_token(user_id)
    
    logger.info(f"User {user_id} refreshed access token")
    
    return AccessTokenResponse(
        access_token=new_access_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )

@app.post("/api/board", response_model=ChatResponseV2)
@limiter.limit("10/minute")
async def board_chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(verify_token),
) -> ChatResponseV2:
    """
    Оптимизированная версия board_chat с единым контрактом.
    Всегда возвращает ChatResponseV2 с agents[], debug-данные только если debug=true.
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

    order = ["ceo", "cfo", "cpo", "marketing", "skeptic"]
    active = req.active_agents if req.active_agents is not None else order
    active_ordered = [a for a in order if a in active]

    compressed_user_msg = compress_user_message(user_msg, user_id=user_id)
    logger.info(
        "Compressed user message | intent=%s | domain=%s | idea_summary=%s",
        compressed_user_msg.intent,
        compressed_user_msg.domain,
        compressed_user_msg.idea_summary,
    )

    replies: List[AgentReplyV2] = []
    ctx: dict[str, dict] = {}

    try:
        for agent in active_ordered:
            parts: List[str] = [
                "СЖАТЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ (JSON):",
                json.dumps(compressed_user_msg.dict(), ensure_ascii=False, indent=2),
            ]

            if ctx:
                parts.append("\nСЖАТЫЕ МНЕНИЯ ДРУГИХ ЧЛЕНОВ СОВЕТА (JSON):")
                for prev_agent in order:
                    if prev_agent in ctx:
                        parts.append(f"{prev_agent}:")
                        parts.append(json.dumps(ctx[prev_agent]["compressed"], ensure_ascii=False, indent=2))

            compressed = compress_history(req.history, max_items=5)
            if compressed:
                parts.append("\nВЫДЕЖКА ИЗ ИСТОРИИ (последние 5 сообщений):")
                parts.append(compressed)

            agent_input = "\n".join(parts)

            raw_response, agent_usage = ask_gigachat(agent, agent_input, track_usage=debug)

            try:
                compressed_response = json.loads(raw_response)
                # Валидация наличия ключевых полей
                if "verdict" not in compressed_response or "confidence" not in compressed_response:
                    logger.warning(
                        "Agent %s returned JSON but missing critical fields | keys=%s",
                        agent,
                        list(compressed_response.keys())
                    )
                    # Создать минимальный fallback
                    compressed_response = {
                        "verdict": "INCOMPLETE",
                        "confidence": 0,
                        "raw_response": raw_response,
                        **compressed_response  # Сохранить оригинальные поля, если есть
                    }
                else:
                    logger.info(
                        "Agent %s returned valid JSON | verdict=%s | confidence=%d",
                        agent,
                        compressed_response.get("verdict", "N/A"),
                        compressed_response.get("confidence", 0),
                    )
            except json.JSONDecodeError as e:
                logger.warning("Agent %s returned non-JSON response: %s | error=%s", agent, raw_response[:100], str(e))
                compressed_response = {
                    "verdict": "NO-DATA",
                    "confidence": 0,
                    "raw_response": raw_response[:500]  # Ограничить размер сохранённого ответа
                }


            ctx[agent] = {"compressed": compressed_response, "usage": agent_usage}

            expanded_text, expander_usage = expand_agent_output(agent, compressed_response, track_usage=debug)

            reply = AgentReplyV2(
                agent=agent,
                text=expanded_text,
            )

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

        if mode == "initial":
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

            raw_summary, summary_usage = ask_gigachat("summary", summary_input, track_usage=debug)

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
                    **compressed_summary  # Сохранить оригинальные поля
                    }
            except json.JSONDecodeError:
                logger.warning("Summary agent returned non-JSON: %s", raw_summary)
                compressed_summary = {
                    "verdict": "NO-DATA", 
                    "confidence": 0,
                    "raw_response": raw_summary[:500]
                }

            expanded_summary, expander_summary_usage = expand_agent_output("summary", compressed_summary, track_usage=debug)

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


@app.post("/api/agent", response_model=AgentReplyV2)
@limiter.limit("20/minute")
async def single_agent(
    req: SingleAgentRequest,
    request: Request,
    user_id: str = Depends(verify_token),
) -> AgentReplyV2:
    """Одиночный агент с отладкой."""
    logger.info(
        "Incoming /api/agent: agent=%s | message=%s | user=%s | debug=%s",
        req.agent,
        (req.message or "")[:50] if req.message else "None",
        user_id,
        req.debug,
    )

    if req.agent not in AGENT_SYSTEM_PROMPTS:
        return AgentReplyV2(agent=req.agent, text=f"Неизвестный агент: {req.agent}")

    parts: List[str] = []

    if req.message:
        compressed_msg = compress_user_message(req.message, user_id=user_id)
        logger.info(
            "Compressed single message | intent=%s | domain=%s",
            compressed_msg.intent,
            compressed_msg.domain,
        )

        parts.extend([
            "СЖАТЫЙ ЗАПРОС (JSON):",
            json.dumps(compressed_msg.dict(), ensure_ascii=False, indent=2),
        ])

    compressed = compress_history(req.history, max_items=5)
    if compressed:
        parts.append("\nВЫДЕЖКА ИЗ ИСТОРИИ (последние 5):")
        parts.append(compressed)

    if not parts:
        parts.append(
            "Проанализируй ситуацию и предложи конкретную идею/замечание от своей роли."
        )

    full_content = "\n".join(parts)

    try:
        raw_response, agent_usage = ask_gigachat(req.agent, full_content, track_usage=req.debug)


        try:
            compressed_response = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Agent %s returned non-JSON: %s", req.agent, raw_response[:100])
            compressed_response = {
                "verdict": "NO-DATA",
                "confidence": 0,
                "raw_response": raw_response[:500]
            }


        expanded_text, expander_usage = expand_agent_output(req.agent, compressed_response, track_usage=req.debug)

        reply = AgentReplyV2(
            agent=req.agent,
            text=expanded_text,
        )

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

        return reply
    except Exception as e:
        logger.exception("Error in /api/agent | agent=%s | user=%s", req.agent, user_id)
        return AgentReplyV2(
            agent=req.agent,
            text=f"Ошибка при обращении к GigaChat для агента {req.agent}: {e}",
        )


@app.post("/api/summary", response_model=AgentReplyV2)
@limiter.limit("10/minute")
async def recalc_summary(
    req: SummaryRequest,
    request: Request,
    user_id: str = Depends(verify_token),
) -> AgentReplyV2:
    """Пересчёт итогов."""
    logger.info(
        "Incoming /api/summary | history_len=%s | user=%s | debug=%s",
        len(req.history) if req.history else 0,
        user_id,
        req.debug,
    )

    compressed = compress_history(req.history, max_items=5)

    if not compressed:
        return AgentReplyV2(
            agent="summary",
            text="Недостаточно истории для пересчёта итогов. Сначала проведите обсуждение."
        )

    summary_input = (
        "Вот выдержка из истории обсуждения совета директоров "
        "(последние 5 сообщений):\n\n"
        f"{compressed}\n\n"
        "Подведи обновлённые итоги по инструкции из system-подсказки."
    )

    try:
        raw_response, summary_usage = ask_gigachat("summary", summary_input, track_usage=req.debug)

        try:
            compressed_response = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Summary returned non-JSON: %s", raw_response[:100])
            compressed_response = {
                "verdict": "NO-DATA",
                "confidence": 0,
                "raw_response": raw_response[:500]
            }

        expanded_text, expander_usage = expand_agent_output("summary", compressed_response, track_usage=req.debug)

        reply = AgentReplyV2(
            agent="summary",
            text=expanded_text,
        )

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

        return reply
    except Exception as e:
        logger.exception("Error in /api/summary | user=%s", user_id)
        return AgentReplyV2(
            agent="summary",
            text=f"Ошибка при обращении к GigaChat для пересчёта итогов: {e}",
        )
