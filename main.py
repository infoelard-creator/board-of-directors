import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
import hashlib
import json
import requests
from fastapi import FastAPI, Request, Depends
from auth import create_access_token, verify_token, TokenResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging
from logging.handlers import RotatingFileHandler
from db import init_db, get_db, create_user_if_not_exists
from sqlalchemy.orm import Session

# ===== Логирование =====

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

# ===== Настройки GigaChat =====

GIGA_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGA_API_BASE = "https://gigachat.devices.sberbank.ru"
GIGA_SCOPE = "GIGACHAT_API_PERS"

GIGA_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")

if not GIGA_AUTH_KEY:
    raise RuntimeError("Не задана переменная окружения GIGACHAT_AUTH_KEY")

_access_token: Optional[str] = None
_access_exp: Optional[datetime] = None

# ===== КЭШ ПАРСЕРА ПО СЕССИЯМ =====
_parsed_cache: dict[str, "ParsedRequest"] = {}


def get_cache_key(user_id: str, message: str) -> str:
    """Генерирует ключ кэша на основе user_id и сообщения."""
    msg_hash = hashlib.md5(message.encode()).hexdigest()[:8]
    return f"{user_id}:{msg_hash}"


def get_cached_parse(user_id: str, message: str) -> Optional["ParsedRequest"]:
    """Получает кэшированный парс запроса."""
    key = get_cache_key(user_id, message)
    cached = _parsed_cache.get(key)
    if cached:
        logger.info("Parser cache hit | user=%s | message=%s", user_id, message[:50])
    return cached


def cache_parse(user_id: str, message: str, parsed: "ParsedRequest") -> None:
    """Кэширует парс запроса."""
    key = get_cache_key(user_id, message)
    _parsed_cache[key] = parsed
    if len(_parsed_cache) > 1000:
        keys_to_delete = list(_parsed_cache.keys())[:-500]
        for k in keys_to_delete:
            del _parsed_cache[k]
        logger.info("Parser cache cleaned | remaining=%d", len(_parsed_cache))


def get_gigachat_token() -> str:
    global _access_token, _access_exp

    if _access_token and _access_exp and datetime.utcnow() < _access_exp:
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

    resp = requests.post(GIGA_AUTH_URL, headers=headers, data=data, timeout=10)

    logger.info(
        "Auth response <- %s | status=%s | body=%s",
        GIGA_AUTH_URL,
        resp.status_code,
        resp.text,
    )

    resp.raise_for_status()
    j = resp.json()
    _access_token = j["access_token"]
    _access_exp = datetime.utcnow() + timedelta(minutes=25)
    return _access_token


# ===== ОПТИМИЗИРОВАННЫЕ ПАРАМЕТРЫ И ПРОМПТЫ =====

AGENT_PARAMS = {
    "ceo": {"temperature": 0.4, "max_tokens": 150, "top_p": 0.9},
    "cfo": {"temperature": 0.3, "max_tokens": 150, "top_p": 0.85},
    "cpo": {"temperature": 0.5, "max_tokens": 150, "top_p": 0.9},
    "marketing": {"temperature": 0.65, "max_tokens": 160, "top_p": 0.95},
    "skeptic": {"temperature": 0.6, "max_tokens": 150, "top_p": 0.9},
    "summary": {"temperature": 0.5, "max_tokens": 300, "top_p": 0.9},
}

AGENT_SYSTEM_PROMPTS = {
    "ceo": (
        "РОЛЬ: CEO. Анализируешь идею из ввода пользователя.
"
        "ВЫХОД (строго в этом порядке):
"
        "1) [Суть идеи] — переформулировка идеи в 1 строке
"
        "2) [Ход] — твой стратегический ход для масштабирования
"
        "3) [Verdict] — GO или NO-GO
"
        "4) [Confidence] — % уверенности
"
        "Фокусируйся на LTV/CAC, runway и стратегии роста из конкретного ввода."
    ),
    "cfo": (
        "РОЛЬ: CFO. Оцениваешь финансовую валидацию идеи пользователя.
"
        "ВЫХОД (строго в этом порядке):
"
        "1) [Гипотеза] — что нужно проверить за деньги
"
        "2) [Бюджет] — минимальный бюджет для теста (в USD)
"
        "3) [Verdict] — FAST или SLOW
"
        "4) [Confidence] — % уверенности
"
        "Ищи метрику, которую можно валидировать за 2 недели дёшево."
    ),
    "cpo": (
        "РОЛЬ: CPO. Ищешь конкурентный дефицит (Moat) в идее пользователя.
"
        "ВЫХОД (строго в этом порядке):
"
        "1) [Продукт] — переформулировка функции в 1 строке
"
        "2) [Moat] — что сложно скопировать за неделю
"
        "3) [Verdict] — SAFE или VULNERABLE
"
        "4) [Confidence] — % уверенности
"
        "Опирайся на конкретные функции из ввода, не используй абстракции."
    ),
    "marketing": (
        "РОЛЬ: VP Marketing. Придумываешь канал роста для этой идеи.
"
        "ВЫХОД (строго в этом порядке):
"
        "1) [Аудитория] — целевая аудитория из ввода
"
        "2) [Хак] — конкретный гроуз-хак (не 'маркетинг')
"
        "3) [Verdict] — SCALABLE или MANUAL
"
        "4) [Confidence] — % уверенности
"
        "Предложи механику, которая работает без найма людей."
    ),
    "skeptic": (
        "РОЛЬ: Skeptic. Находишь фатальную дыру в идее пользователя.
"
        "ВЫХОД (строго в этом порядке):
"
        "1) [Слабое место] — самое уязвимое утверждение в идее
"
        "2) [Краш-тест] — как это убить за <$1K
"
        "3) [Verdict] — FATAL или FIXABLE
"
        "4) [Confidence] — % уверенности
"
        "Атакуй конкретные утверждения пользователя, не общие критики."
    ),
    "summary": (
        "РОЛЬ: Модератор. Синтезируешь мнения совета по ЕДИНОЙ идее.
"
        "ВЫХОД (строго в этом порядке):
"
        "1) [Идея] — суть в 1 строке
"
        "2) [Плюсы] — 2-3 лучших инсайта совета
"
        "3) [Риски] — 2-3 главных опасности
"
        "4) [ИТОГ] — Перспективно ли? (Recommend Go/No-Go + % уверенности)
"
        "Пиши структурировано, ссылайся на мнения агентов."
    ),
}

# ===== ПАРСЕР ИСХОДНОГО ЗАПРОСА =====

PARSER_SYSTEM_PROMPT = (
    "РОЛЬ: Parser. Структурируешь исходный запрос пользователя.
"
    "ВЫХОД (JSON, строго в этом формате):
"
    "{
"
    '  "intent": "validate_idea|find_risks|scale_strategy|compare_ideas|other",
'
    '  "domain": "product|finance|marketing|strategy|operations|hr",
'
    '  "key_points": ["точка 1", "точка 2"],
'
    '  "assumptions": ["предположение 1"],
'
    '  "constraints": ["ограничение 1"],
'
    '  "summary": "одно предложение о сути запроса"
'
    "}
"
    "Требования:
"
    "- intent: конкретная цель пользователя
"
    "- domain: один из списка
"
    "- key_points: 2-5 главных утверждений
"
    "- assumptions: что неявно предполагает пользователь
"
    "- constraints: бюджет, сроки, команда, ресурсы
"
    "- summary: суть в 1 строке
"
    "Отвечай ТОЛЬКО JSON, без комментариев."
)


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


def parse_user_request(user_msg: str, user_id: str = "anonymous") -> ParsedRequest:
    """
    Парсит исходный запрос пользователя в структурированную форму.
    Использует кэш для экономии API вызовов.
    """
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

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
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


def compress_history(history: Optional[List[str]], max_items: int = 5) -> str:
    """Сжимает историю до последних N сообщений для экономии токенов."""
    if not history:
        return ""
    recent = history[-max_items:]
    return "
".join(recent)


def ask_gigachat(agent: str, user_msg: str) -> str:
    """
    Запрос к GigaChat с оптимизированными параметрами.
    user_msg уже содержит все необходимые данные.
    """
    token = get_gigachat_token()
    system_prompt = AGENT_SYSTEM_PROMPTS[agent]
    params = AGENT_PARAMS[agent]

    agent_input = user_msg

    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": agent_input},
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

    logger.info(
        "Chat request -> %s | agent=%s | temp=%.1f | max_tokens=%d",
        url,
        agent,
        params["temperature"],
        params["max_tokens"],
    )

    resp = requests.post(url, headers=headers, json=payload, timeout=60)

    logger.info(
        "Chat response <- %s | agent=%s | status=%s",
        url,
        agent,
        resp.status_code,
    )

    resp.raise_for_status()
    j = resp.json()
    return j["choices"][0]["message"]["content"].strip()


# ===== FastAPI-приложение =====

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()


@app.on_event("startup")
def on_startup():
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

# ===== Модели =====


class ChatRequest(BaseModel):
    message: str
    active_agents: Optional[List[str]] = None
    history: Optional[List[str]] = None
    mode: Optional[str] = None


class AgentReply(BaseModel):
    agent: str
    text: str


class SingleAgentRequest(BaseModel):
    agent: str
    message: Optional[str] = None
    history: Optional[List[str]] = None


class SingleAgentReply(BaseModel):
    text: str


class SummaryRequest(BaseModel):
    history: Optional[List[str]] = None


class SummaryReply(BaseModel):
    text: str


class LoginRequest(BaseModel):
    user_id: str


@app.post("/api/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
):
    """Логин: принимает user_id, создаёт пользователя, возвращает JWT."""
    create_user_if_not_exists(db, body.user_id)
    token = create_access_token(body.user_id)
    return TokenResponse(access_token=token)


# ===== ОПТИМИЗИРОВАННАЯ ЦЕПОЧКА СОВЕТА С ПАРСЕРОМ И КЭШЕМ =====


@app.post("/api/board", response_model=List[AgentReply])
@limiter.limit("10/minute")
async def board_chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):
    """
    Оптимизированная версия board_chat с парсером и кэшем.
    1. Парсим исходный запрос пользователя (с кэшем).
    2. Все агенты получают структурированный запрос.
    """
    user_msg = req.message
    mode = req.mode or "initial"

    logger.info(
        "Incoming /api/board message: %s | active_agents=%s | mode=%s | user=%s",
        user_msg[:50],
        req.active_agents,
        mode,
        user_id,
    )

    order = ["ceo", "cfo", "cpo", "marketing", "skeptic"]
    active = req.active_agents if req.active_agents is not None else order
    active_ordered = [a for a in order if a in active]

    replies: List[AgentReply] = []
    ctx: dict[str, str] = {}

    try:
        parsed_request = parse_user_request(user_msg, user_id=user_id)
        logger.info(
            "Parsed request | intent=%s | domain=%s | key_points=%s",
            parsed_request.intent,
            parsed_request.domain,
            parsed_request.key_points,
        )

        for agent in active_ordered:
            parts: List[str] = [
                "СТРУКТУРИРОВАННЫЙ ЗАПРОС (из парсера):",
                f"• Цель: {parsed_request.intent}",
                f"• Область: {parsed_request.domain}",
                f"• Ключевые точки: {', '.join(parsed_request.key_points) if parsed_request.key_points else 'нет'}",
                f"• Предположения: {', '.join(parsed_request.assumptions) if parsed_request.assumptions else 'нет'}",
                f"• Ограничения: {', '.join(parsed_request.constraints) if parsed_request.constraints else 'нет'}",
                f"• Краткое резюме: {parsed_request.summary or parsed_request.original_message[:200]}",
            ]

            compressed = compress_history(req.history, max_items=5)
            if compressed:
                parts.append(
                    f"
ВЫДЕЖКА ИЗ ИСТОРИИ (последние 5 сообщений):
{compressed}"
                )

            if ctx:
                parts.append("
МНЕНИЯ ДРУГИХ ЧЛЕНОВ СОВЕТА:")
                for prev_agent in order:
                    if prev_agent in ctx:
                        parts.append(f"{prev_agent.upper()}: {ctx[prev_agent]}")

            agent_input = "
".join(parts)
            text = ask_gigachat(agent, agent_input)
            ctx[agent] = text
            replies.append(AgentReply(agent=agent, text=text))

        if mode == "initial":
            summary_parts: List[str] = [
                "СТРУКТУРИРОВАННЫЙ ЗАПРОС:",
                f"• Цель: {parsed_request.intent}",
                f"• Область: {parsed_request.domain}",
                f"• Ключевые точки: {', '.join(parsed_request.key_points) if parsed_request.key_points else 'нет'}",
                "",
                "МНЕНИЯ СОВЕТА:",
            ]
            for agent in active_ordered:
                if agent in ctx:
                    summary_parts.append(f"{agent.upper()}: {ctx[agent]}")

            compressed = compress_history(req.history, max_items=5)
            if compressed:
                summary_parts.append("
ВЫДЕЖКА ИЗ ИСТОРИИ:
" + compressed)

            summary_input = "
".join(summary_parts)
            summary_text = ask_gigachat("summary", summary_input)
            replies.append(AgentReply(agent="summary", text=summary_text))

    except Exception as e:
        logger.exception("Error while calling GigaChat board chain | user=%s", user_id)
        replies.append(
            AgentReply(agent="error", text=f"Ошибка при обращении к GigaChat: {e}")
        )

    logger.info(
        "Outgoing /api/board | agents=%s | reply_count=%d",
        active_ordered,
        len(replies),
    )
    return replies


@app.post("/api/agent", response_model=SingleAgentReply)
@limiter.limit("20/minute")
async def single_agent(
    req: SingleAgentRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):
    """Одиночный агент с парсером (если передано сообщение) + сокращённой историей."""
    logger.info(
        "Incoming /api/agent: agent=%s | message=%s | user=%s",
        req.agent,
        (req.message or "")[:50] if req.message else "None",
        user_id,
    )

    if req.agent not in AGENT_SYSTEM_PROMPTS:
        return SingleAgentReply(text=f"Неизвестный агент: {req.agent}")

    parts: List[str] = []

    if req.message:
        parsed_request = parse_user_request(req.message, user_id=user_id)
        logger.info(
            "Parsed single message | intent=%s | domain=%s",
            parsed_request.intent,
            parsed_request.domain,
        )
        parts.extend(
            [
                "СТРУКТУРИРОВАННЫЙ ЗАПРОС:",
                f"• Цель: {parsed_request.intent}",
                f"• Область: {parsed_request.domain}",
                f"• Ключевые точки: {', '.join(parsed_request.key_points) if parsed_request.key_points else 'нет'}",
                f"• Предположения: {', '.join(parsed_request.assumptions) if parsed_request.assumptions else 'нет'}",
                f"• Ограничения: {', '.join(parsed_request.constraints) if parsed_request.constraints else 'нет'}",
                f"• Краткое резюме: {parsed_request.summary or parsed_request.original_message[:200]}",
            ]
        )

    compressed = compress_history(req.history, max_items=5)
    if compressed:
        parts.append("
ВЫДЕЖКА ИЗ ИСТОРИИ (последние 5):
" + compressed)

    if not parts:
        parts.append(
            "Проанализируй ситуацию и предложи конкретную идею/замечание от своей роли."
        )

    full_content = "
".join(parts)

    try:
        text = ask_gigachat(req.agent, full_content)
    except Exception as e:
        logger.exception("Error in /api/agent | agent=%s | user=%s", req.agent, user_id)
        text = f"Ошибка при обращении к GigaChat для агента {req.agent}: {e}"

    return SingleAgentReply(text=text)


@app.post("/api/summary", response_model=SummaryReply)
@limiter.limit("10/minute")
async def recalc_summary(
    req: SummaryRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):
    """Пересчёт итогов на основе последней истории обсуждения."""
    logger.info(
        "Incoming /api/summary | history_len=%s | user=%s",
        len(req.history) if req.history else 0,
        user_id,
    )

    compressed = compress_history(req.history, max_items=5)

    if not compressed:
        return SummaryReply(
            text="Недостаточно истории для пересчёта итогов. Сначала проведите обсуждение."
        )

    summary_input = (
        "Вот выдержка из истории обсуждения совета директоров "
        "(последние 5 сообщений):

"
        f"{compressed}

"
        "Подведи обновлённые итоги по инструкции из system-подсказки."
    )

    try:
        text = ask_gigachat("summary", summary_input)
    except Exception as e:
        logger.exception("Error in /api/summary | user=%s", user_id)
        text = f"Ошибка при обращении к GigaChat для пересчёта итогов: {e}"

    return SummaryReply(text=text)
