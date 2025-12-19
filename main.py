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


# ===== Настройки ролей совета =====

AGENT_SYSTEM_PROMPTS = {
    "ceo": (
        "ЗАДАЧА: Найти стратегический рычаг — где капитал даёт максимальный мультипликатор.\n"
        "ШАГ 1: Сгенерируй 2–3 радикально разных стратегических хода (новые рынки, модели дохода, формат продукта).\n"
        "ШАГ 2: Выбери один как основной и оцени.\n"
        "CONSTRAINT: LTV/CAC < 3 ИЛИ runway с текущим Burn Rate < следующего раунда → RED FLAG.\n"
        "ВЫХОД: [Идея] | [Verdict: GO/NO-GO/PIVOT] | [Ключевая гипотеза] | [Как проверить <$5K] | [Confidence: X%].\n"
        "Макс 70 слов. Беспощаден в выводах, смел в идеях."
    ),
    "cfo": (
        "ЗАДАЧА: Сжать время до валидации без сжигания лишнего кэша.\n"
        "ШАГ 1: Предложи 1–2 способа удешевить ту же гипотезу (другой канал, более дешёвая выборка, ручной эксперимент).\n"
        "ШАГ 2: Оцени текущий план vs твоя альтернатива по кэшу и скорости.\n"
        "CONSTRAINT: Нет ощутимого результата/метрики за 2 недели → БЛОКЕР.\n"
        "ВЫХОД: [Verdict: FAST/SLOW] | [Главный тормоз] | [Дешёвая альтернатива] | [Что выкинуть из MVP] | [Confidence: X%].\n"
        "Макс 70 слов. Скорость и бюджет важнее перфекционизма."
    ),
    "cpo": (
        "ЗАДАЧА: Найти нечестное конкурентное преимущество (Moat), за которое будут платить.\n"
        "ШАГ 1: Придумай 2–3 'мутации' продукта (новый пакет, формат доставки ценности, сегмент) с потенциалом Moat.\n"
        "ШАГ 2: Оцени, какая мутация даёт лучший Moat.\n"
        "CONSTRAINT: Если это может скопировать небольшая команда за выходные → Moat = 0.\n"
        "ВЫХОД: [Идея] | [Verdict: SAFE/VULNERABLE] | [Тип преимущества] | [Вектор атаки конкурентов] | [Confidence: X%].\n"
        "Макс 70 слов. Паранойя обязательна, но ты всё ещё изобретаешь."
    ),
    "marketing": (
        "ЗАДАЧА: Обеспечить масштабирование без ручного труда в основном цикле ценности.\n"
        "ШАГ 1: Сгенерируй 2–3 нестандартных канала или механики роста (партнёрства, продуктовый growth, рефералки, контент‑мемы).\n"
        "ШАГ 2: Выбери один как основной и оцени масштабируемость.\n"
        "CONSTRAINT: Если рост пользователей линейно тянет людей/часы → запрет на scale.\n"
        "ВЫХОД: [Идея] | [Verdict: SCALABLE/MANUAL] | [Узкое место] | [Рычаг автоматизации] | [Confidence: X%].\n"
        "Макс 70 слов. Думай как инфраструктура, но придумывай как хакер."
    ),
    "skeptic": (
        "ЗАДАЧА: Вскрыть фатальное недоказанное предположение ДО взлёта.\n"
        "ШАГ 1: Назови ≥1 ключевое предположение, без которого всё рушится.\n"
        "ШАГ 2: Придумай минимальный жёсткий тест, который может его опровергнуть.\n"
        "Если не можешь — явно запроси недостающие данные.\n"
        "ВЫХОД: [Assumption] | [Способ отказа] | [MVT: проверить <$1K и <2 недель] | [Confidence: X%].\n"
        "Макс 70 слов. Ломаешь, но через эксперимент."
    ),
    "summary": (
        "Ты модератор неформальной брейншторм-сессии пяти ролей (CEO, CFO, CPO, маркетинг, скептик).\n"
        "У тебя есть история обсуждения и ответы ролей. Твоя задача — кратко подвести итоги.\n"
        "Сделай структурированное резюме:\n"
        "1) Список уникальных идей (по 1 строке на идею).\n"
        "2) Для каждой идеи: ключевые плюсы.\n"
        "3) Для каждой идеи: ключевые минусы/риски.\n"
        "4) Какие 1–2 идеи выглядят самыми перспективными и почему.\n"
        "Пиши максимально конкретно, без воды и общих фраз. Объём — до 200 слов."
    ),
}


def ask_gigachat(agent: str, user_msg: str) -> str:
    token = get_gigachat_token()
    system_prompt = AGENT_SYSTEM_PROMPTS[agent]

    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    url = f"{GIGA_API_BASE}/api/v1/chat/completions"

    logger.info(
        "Chat request -> %s | agent=%s | headers=%s | payload=%s",
        url,
        agent,
        {k: (v if k != "Authorization" else "***hidden***") for k, v in headers.items()},
        payload,
    )

    resp = requests.post(url, headers=headers, json=payload, timeout=60)

    logger.info(
        "Chat response <- %s | agent=%s | status=%s | body=%s",
        url,
        agent,
        resp.status_code,
        resp.text,
    )

    resp.raise_for_status()
    j = resp.json()
    return j["choices"][0]["message"]["content"].strip()


# ===== FastAPI-приложение =====

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()

origins = [
    "http://45.151.31.180:8080",
    "http://localhost:8080",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["POST"],  # тебе по факту нужны только POST
    allow_headers=["Content-Type", "Authorization"],
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ===== Модели =====

class ChatRequest(BaseModel):
    message: str
    active_agents: list[str] | None = None
    history: list[str] | None = None
    mode: str | None = None  # "initial" | "comment"


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

# ===== JWT login =====

@app.post("/api/login", response_model=TokenResponse)
async def login(user_id: str):
    """
    Простой логин: принимает user_id (строка), возвращает JWT-токен.
    """
    token = create_access_token(user_id)
    return TokenResponse(access_token=token)


# ===== Основная цепочка совета директоров =====

@app.post("/api/board", response_model=List[AgentReply])
@limiter.limit("10/minute")
async def board_chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):

    """
    mode = "initial"  — первый раунд: активные агенты + summary.
    mode = "comment"  — комментарий: только активные агенты, без нового summary.
    """
    user_msg = req.message
    mode = req.mode or "initial"
    logger.info(
        "Incoming /api/board message: %s | active_agents=%s | mode=%s",
        user_msg,
        req.active_agents,
        mode,
    )

    order = ["ceo", "cfo", "cpo", "marketing", "skeptic"]

    active = req.active_agents or order
    active_ordered = [a for a in order if a in active]

    replies: list[AgentReply] = []
    ctx: dict[str, str] = {}

    try:
        def build_agent_input(agent_name: str) -> str:
            parts: list[str] = []

            if mode == "comment":
                parts.append(f"Текущий комментарий пользователя:\n{user_msg}")
                if req.history:
                    history_text = "\n".join(req.history[-20:])
                    parts.append(
                        "Фрагменты предыдущей дискуссии (хронологически):\n" + history_text
                    )
                parts.append(
                    "Дай ответ на комментарий, учитывая контекст выше, но опираясь прежде всего на текущий комментарий."
                )
            else:
                parts.append(f"Запрос пользователя:\n{user_msg}")

            if ctx:
                for prev in order:
                    if prev in ctx:
                        parts.append(f"Ответ {prev.upper()}:\n{ctx[prev]}")

            return "\n\n".join(parts)

        for agent in active_ordered:
            agent_input = build_agent_input(agent)
            text = ask_gigachat(agent, agent_input)
            ctx[agent] = text
            replies.append(AgentReply(agent=agent, text=text))

        if mode == "initial":
            summary_parts = [f"Запрос пользователя:\n{user_msg}"]
            for agent in order:
                if agent in ctx:
                    summary_parts.append(f"Ответ {agent.upper()}:\n{ctx[agent]}")
            if req.history:
                history_text = "\n".join(req.history[-20:])
                summary_parts.append(
                    f"История обсуждения (последние 20 сообщений):\n{history_text}"
                )

            summary_input = "\n\n".join(summary_parts)
            summary_text = ask_gigachat("summary", summary_input)
            replies.append(AgentReply(agent="summary", text=summary_text))

    except Exception as e:
        logger.exception("Error while calling GigaChat board chain")
        replies.append(
            AgentReply(agent="error", text=f"Ошибка при обращении к GigaChat: {e}")
        )

    logger.info("Outgoing /api/board replies: %s", replies)
    return replies


# ===== Перезапуск одного агента по истории =====

@app.post("/api/agent", response_model=SingleAgentReply)
@limiter.limit("20/minute")
async def single_agent(
    req: SingleAgentRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):


    logger.info(
        "Incoming /api/agent: agent=%s | message=%s",
        req.agent,
        req.message,
    )

    if req.agent not in AGENT_SYSTEM_PROMPTS:
        return SingleAgentReply(text=f"Неизвестный агент: {req.agent}")

    history_text = ""
    if req.history:
        history_text = "\n".join(req.history[-20:])

    parts: list[str] = []
    if req.message:
        parts.append(f"Текущий запрос пользователя:\n{req.message}")
    if history_text:
        parts.append(f"История обсуждения (последние 20 сообщений):\n{history_text}")

    if not parts:
        parts.append(
            "Проанализируй ситуацию и предложи ещё одну конкретную идею/замечание от своей роли."
        )

    full_content = "\n\n".join(parts)

    try:
        text = ask_gigachat(req.agent, full_content)
    except Exception as e:
        logger.exception("Error while calling GigaChat for single agent=%s", req.agent)
        text = f"Ошибка при обращении к GigaChat для агента {req.agent}: {e}"

    return SingleAgentReply(text=text)


# ===== Пересчёт итогов по истории =====

@app.post("/api/summary", response_model=SummaryReply)
@limiter.limit("10/minute")
async def recalc_summary(
    req: SummaryRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):


    """
    Пересчёт итогов по истории обсуждения.
    Берём последние 20 сообщений из history и просим summary-агента
    подвести новые итоги.
    """
    logger.info(
        "Incoming /api/summary | history_len=%s",
        len(req.history) if req.history else 0,
    )

    history_text = ""
    if req.history:
        history_text = "\n".join(req.history[-20:])

    if not history_text:
        return SummaryReply(
            text="Недостаточно истории для пересчёта итогов. Сначала проведите обсуждение."
        )

    summary_input = (
        "Вот выдержка из истории обсуждения совета директоров "
        "(последние сообщения, в хронологическом порядке):\n\n"
        f"{history_text}\n\n"
        "Подведи обновлённые итоги с учётом всего обсуждения по инструкции из system-подсказки."
    )

    try:
        text = ask_gigachat("summary", summary_input)
    except Exception as e:
        logger.exception("Error while calling GigaChat for /api/summary")
        text = f"Ошибка при обращении к GigaChat для пересчёта итогов: {e}"

    return SummaryReply(text=text)
