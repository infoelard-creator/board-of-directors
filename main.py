import os
import uuid
from datetime import datetime, timedelta
from typing import List

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

_access_token: str | None = None
_access_exp: datetime | None = None


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

# Параметры температуры, max_tokens и top_p для каждой роли
AGENT_PARAMS = {
    "ceo": {
        "temperature": 0.4,
        "max_tokens": 150,
        "top_p": 0.9,
    },
    "cfo": {
        "temperature": 0.3,
        "max_tokens": 150,
        "top_p": 0.85,
    },
    "cpo": {
        "temperature": 0.5,
        "max_tokens": 150,
        "top_p": 0.9,
    },
    "marketing": {
        "temperature": 0.65,
        "max_tokens": 160,
        "top_p": 0.95,
    },
    "skeptic": {
        "temperature": 0.6,
        "max_tokens": 150,
        "top_p": 0.9,
    },
    "summary": {
        "temperature": 0.5,
        "max_tokens": 300,
        "top_p": 0.9,
    },
}

# СОКРАЩЁННЫЕ И УЛУЧШЕННЫЕ ПРОМПТЫ
AGENT_SYSTEM_PROMPTS = {
    "ceo": (
        "РОЛЬ: CEO. Анализируешь идею из ввода пользователя.\n"
        "ВЫХОД (строго в этом порядке):\n"
        "1) [Суть идеи] — переформулировка идеи в 1 строке\n"
        "2) [Ход] — твой стратегический ход для масштабирования\n"
        "3) [Verdict] — GO или NO-GO\n"
        "4) [Confidence] — % уверенности\n"
        "Фокусируйся на LTV/CAC, runway и стратегии роста из конкретного ввода."
    ),
    "cfo": (
        "РОЛЬ: CFO. Оцениваешь финансовую валидацию идеи пользователя.\n"
        "ВЫХОД (строго в этом порядке):\n"
        "1) [Гипотеза] — что нужно проверить за деньги\n"
        "2) [Бюджет] — минимальный бюджет для теста (в USD)\n"
        "3) [Verdict] — FAST или SLOW\n"
        "4) [Confidence] — % уверенности\n"
        "Ищи метрику, которую можно валидировать за 2 недели дёшево."
    ),
    "cpo": (
        "РОЛЬ: CPO. Ищешь конкурентный дефицит (Moat) в идее пользователя.\n"
        "ВЫХОД (строго в этом порядке):\n"
        "1) [Продукт] — переформулировка функции в 1 строке\n"
        "2) [Moat] — что сложно скопировать за неделю\n"
        "3) [Verdict] — SAFE или VULNERABLE\n"
        "4) [Confidence] — % уверенности\n"
        "Опирайся на конкретные функции из ввода, не используй абстракции."
    ),
    "marketing": (
        "РОЛЬ: VP Marketing. Придумываешь канал роста для этой идеи.\n"
        "ВЫХОД (строго в этом порядке):\n"
        "1) [Аудитория] — целевая аудитория из ввода\n"
        "2) [Хак] — конкретный гроуз-хак (не 'маркетинг')\n"
        "3) [Verdict] — SCALABLE или MANUAL\n"
        "4) [Confidence] — % уверенности\n"
        "Предложи механику, которая работает без найма людей."
    ),
    "skeptic": (
        "РОЛЬ: Skeptic. Находишь фатальную дыру в идее пользователя.\n"
        "ВЫХОД (строго в этом порядке):\n"
        "1) [Слабое место] — самое уязвимое утверждение в идее\n"
        "2) [Краш-тест] — как это убить за <$1K\n"
        "3) [Verdict] — FATAL или FIXABLE\n"
        "4) [Confidence] — % уверенности\n"
        "Атакуй конкретные утверждения пользователя, не общие критики."
    ),
    "summary": (
        "РОЛЬ: Модератор. Синтезируешь мнения совета по ЕДИНОЙ идее.\n"
        "ВЫХОД (строго в этом порядке):\n"
        "1) [Идея] — суть в 1 строке\n"
        "2) [Плюсы] — 2-3 лучших инсайта совета\n"
        "3) [Риски] — 2-3 главных опасности\n"
        "4) [ИТОГ] — Перспективно ли? (Recommend Go/No-Go + % уверенности)\n"
        "Пиши структурировано, ссылайся на мнения агентов."
    ),
}


def compress_history(history: list[str] | None, max_items: int = 5) -> str:
    """Сжимает историю до последних N сообщений для экономии токенов."""
    if not history:
        return ""
    
    recent = history[-max_items:]
    return "\n".join(recent)


def ask_gigachat(agent: str, user_msg: str) -> str:
    """
    Запрос к GigaChat с оптимизированными параметрами.
    - Добавлены temperature, max_tokens, top_p
    """
    token = get_gigachat_token()
    system_prompt = AGENT_SYSTEM_PROMPTS[agent]
    params = AGENT_PARAMS[agent]

    payload = {
        "model": "GigaChat-2",
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
    active_agents: list[str] | None = None
    history: list[str] | None = None
    mode: str | None = None


class AgentReply(BaseModel):
    agent: str
    text: str


class SingleAgentRequest(BaseModel):
    agent: str
    message: str | None = None
    history: list[str] | None = None


class SingleAgentReply(BaseModel):
    text: str


class SummaryRequest(BaseModel):
    history: list[str] | None = None


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


# ===== ОПТИМИЗИРОВАННАЯ ЦЕПОЧКА СОВЕТА =====

@app.post("/api/board", response_model=List[AgentReply])
@limiter.limit("10/minute")
async def board_chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):
    """
    Оптимизированная версия board_chat:
    - Сокращена история (max 5 сообщений)
    - Убрано дублирование контекста между агентами
    - Параметры качества в payload (temperature, max_tokens, top_p)
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
    active = req.active_agents or order
    active_ordered = [a for a in order if a in active]

    replies: list[AgentReply] = []
    ctx: dict[str, str] = {}

    try:
        # ШАГ 1: Собираем ответы от всех агентов
        for agent in active_ordered:
            parts: list[str] = [
                f"ИСХОДНЫЙ ЗАПРОС:\n{user_msg}"
            ]
            
            # Сжатая история (только последние 5 сообщений)
            compressed = compress_history(req.history, max_items=5)
            if compressed:
                parts.append(
                    f"ВЫДЕРЖКА ИЗ ИСТОРИИ (последние 5 сообщений):\n{compressed}"
                )
            
            # Мнения уже опрошенных агентов
            if ctx:
                parts.append("МНЕНИЯ ДРУГИХ ЧЛЕНОВ СОВЕТА:")
                for prev_agent in order:
                    if prev_agent in ctx:
                        parts.append(f"{prev_agent.upper()}: {ctx[prev_agent]}")
            
            agent_input = "\n\n".join(parts)
            text = ask_gigachat(agent, agent_input)
            ctx[agent] = text
            replies.append(AgentReply(agent=agent, text=text))

        # ШАГ 2: Если режим "initial", добавляем summary
        if mode == "initial":
            summary_parts: list[str] = [
                f"ИСХОДНЫЙ ЗАПРОС:\n{user_msg}"
            ]
            
            # Добавляем ответы агентов
            summary_parts.append("МНЕНИЯ СОВЕТА:")
            for agent in active_ordered:
                if agent in ctx:
                    summary_parts.append(f"{agent.upper()}: {ctx[agent]}")
            
            # Сжатая история
            compressed = compress_history(req.history, max_items=5)
            if compressed:
                summary_parts.append(
                    f"ВЫДЕРЖКА ИЗ ИСТОРИИ:\n{compressed}"
                )
            
            summary_input = "\n\n".join(summary_parts)
            summary_text = ask_gigachat("summary", summary_input)
            replies.append(AgentReply(agent="summary", text=summary_text))

    except Exception as e:
        logger.exception("Error while calling GigaChat board chain | user=%s", user_id)
        replies.append(
            AgentReply(agent="error", text=f"Ошибка при обращении к GigaChat: {e}")
        )

    logger.info("Outgoing /api/board | agents=%s | reply_count=%d", active_ordered, len(replies))
    return replies


@app.post("/api/agent", response_model=SingleAgentReply)
@limiter.limit("20/minute")
async def single_agent(
    req: SingleAgentRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):
    """Переделал: сокращена история (max 5 сообщений вместо 20)"""
    logger.info(
        "Incoming /api/agent: agent=%s | message=%s | user=%s",
        req.agent,
        req.message[:50] if req.message else "None",
        user_id,
    )

    if req.agent not in AGENT_SYSTEM_PROMPTS:
        return SingleAgentReply(text=f"Неизвестный агент: {req.agent}")

    parts: list[str] = []
    if req.message:
        parts.append(f"ТЕКУЩИЙ ЗАПРОС:\n{req.message}")

    # Сжатая история (экономим токены!)
    compressed = compress_history(req.history, max_items=5)
    if compressed:
        parts.append(f"ВЫДЕРЖКА ИЗ ИСТОРИИ (последние 5):\n{compressed}")

    if not parts:
        parts.append(
            "Проанализируй ситуацию и предложи конкретную идею/замечание от своей роли."
        )

    full_content = "\n\n".join(parts)

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
    """Пересчёт итогов: сокращена история (max 5 сообщений вместо 20)"""
    logger.info(
        "Incoming /api/summary | history_len=%s | user=%s",
        len(req.history) if req.history else 0,
        user_id,
    )

    # Сжатая история (экономим!)
    compressed = compress_history(req.history, max_items=5)

    if not compressed:
        return SummaryReply(
            text="Недостаточно истории для пересчёта итогов. Сначала проведите обсуждение."
        )

    summary_input = (
        "Вот выдержка из истории обсуждения совета директоров "
        "(последние 5 сообщений):\n\n"
        f"{compressed}\n\n"
        "Подведи обновлённые итоги по инструкции из system-подсказки."
    )

    try:
        text = ask_gigachat("summary", summary_input)
    except Exception as e:
        logger.exception("Error in /api/summary | user=%s", user_id)
        text = f"Ошибка при обращении к GigaChat для пересчёта итогов: {e}"

    return SummaryReply(text=text)
