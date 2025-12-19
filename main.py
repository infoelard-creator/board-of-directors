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
        "РОЛЬ: Ты CEO. Твой стартап описан пользователем.\n"
        "ЗАДАЧА: Проанализируй ВВОД ПОЛЬЗОВАТЕЛЯ и найди стратегический рычаг ИМЕННО ДЛЯ ЭТОЙ ИДЕИ.\n"
        "ШАГ 1: Сгенерируй 2–3 хода для масштабирования ЭТОГО продукта (рынки, модель, формат).\n"
        "ШАГ 2: Выбери лучший.\n"
        "CONSTRAINT: LTV/CAC < 3 или слабый runway → RED FLAG.\n"
        "ВЫХОД: [Суть идеи юзера] | [Твой ход] | [Verdict: GO/NO-GO] | [Гипотеза] | [Confidence: X%].\n"
        "Макс 70 слов. Работай строго по контексту пользователя."
    ),
    "cfo": (
        "РОЛЬ: Ты CFO. Оцениваешь бюджет идеи, которую прислал пользователь.\n"
        "ЗАДАЧА: Сжать валидацию ЭТОЙ идеи до копеек.\n"
        "ШАГ 1: Предложи способ проверить ИМЕННО ЭТУ гипотезу дешевле/быстрее.\n"
        "ШАГ 2: Сравни с планом пользователя.\n"
        "CONSTRAINT: Нет метрики за 2 недели → БЛОКЕР.\n"
        "ВЫХОД: [Анализ ввода] | [Verdict: FAST/SLOW] | [Главный тормоз] | [Дешёвая альтернатива] | [Confidence: X%].\n"
        "Макс 70 слов. Ссылайся на детали из ввода."
    ),
    "cpo": (
        "РОЛЬ: Ты CPO. Ищешь Moat (ров) для продукта из сообщения пользователя.\n"
        "ЗАДАЧА: Найти нечестное преимущество для ОПИСАННОГО продукта.\n"
        "ШАГ 1: Придумай 2–3 «мутации» ЭТОЙ идеи, которые сложно скопировать.\n"
        "ШАГ 2: Оцени лучшую.\n"
        "CONSTRAINT: Копируется за выходные → Moat = 0.\n"
        "ВЫХОД: [Исходный продукт] | [Мутация] | [Verdict: SAFE/VULNERABLE] | [Тип защиты] | [Confidence: X%].\n"
        "Макс 70 слов. Отталкивайся от функций, описанных юзером."
    ),
    "marketing": (
        "РОЛЬ: Ты Маркетолог. Думаешь, как растить ЭТОТ продукт (из ввода пользователя).\n"
        "ЗАДАЧА: Масштабирование ОПИСАННОЙ идеи без ручного труда.\n"
        "ШАГ 1: Придумай хак роста (канал, механика) специально для ЭТОЙ аудитории.\n"
        "ШАГ 2: Оцени масштабируемость.\n"
        "CONSTRAINT: Линейный найм для роста → ЗАПРЕТ.\n"
        "ВЫХОД: [Аудитория из ввода] | [Гроуз-хак] | [Verdict: SCALABLE/MANUAL] | [Рычаг] | [Confidence: X%].\n"
        "Макс 70 слов. Не предлагай абстракцию, бери суть из запроса."
    ),
    "skeptic": (
        "РОЛЬ: Скептик. Ты должен убить идею пользователя.\n"
        "ЗАДАЧА: Вскрыть фатальное заблуждение в ОПИСАНИИ пользователя.\n"
        "ШАГ 1: Назови самое слабое место в ЭТОМ тексте.\n"
        "ШАГ 2: Придумай тест на уничтожение.\n"
        "ВЫХОД: [Слабое место ввода] | [Способ краха] | [MVT: тест <$1K] | [Confidence: X%].\n"
        "Макс 70 слов. Атакуй конкретные утверждения юзера."
    ),
    "summary": (
        "Ты модератор. У тебя есть идея пользователя и 5 мнений совета.\n"
        "ЗАДАЧА: Сведи всё к конкретике по ЭТОМУ проекту.\n"
        "1) Суть идеи (1 строка).\n"
        "2) Лучшие инсайты совета (плюсы).\n"
        "3) Главные риски (минусы).\n"
        "4) ИТОГ: Перспективно или нет.\n"
        "Пиши сжато. Макс 200 слов. Ссылайся на детали обсуждения."
    ),
}


def ask_gigachat(agent: str, user_msg: str) -> str:
    token = get_gigachat_token()
    system_prompt = AGENT_SYSTEM_PROMPTS[agent]

    # 1) усиливаем внимание к описанию пользователя
    formatted_user_msg = (
        "ОПИСАНИЕ ПРОЕКТА/СИТУАЦИИ ПОЛЬЗОВАТЕЛЯ.\n"
        "Опирайся на него в ответе строго в рамках своей роли.\n\n"
        f"{user_msg}"
    )

    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": formatted_user_msg},
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

from pydantic import BaseModel

class LoginRequest(BaseModel):
    user_id: str

@app.post("/api/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """
    Простой логин: принимает user_id в JSON, возвращает JWT-токен.
    """
    token = create_access_token(body.user_id)
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

            # 1. всегда поднимаем исходный запрос наверх
            parts.append(
                "ИСХОДНЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ "
                "(это главная точка опоры, не меняй её формулировку по смыслу):\n"
                f"{user_msg}"
            )

            # 2. поясняем режим
            if mode == "comment":
                parts.append(
                    "ТЕКУЩИЙ КОММЕНТАРИЙ ПОЛЬЗОВАТЕЛЯ "
                    "(уточнение к исходному запросу):\n"
                    f"{user_msg}"
                )
                parts.append(
                    "Сначала кратко переформулируй исходный запрос (1 строка), "
                    "затем прокомментируй этот комментарий, опираясь на исходный запрос."
                )
            else:
                parts.append(
                    "Твоя задача — ответить на этот исходный запрос в рамках своей роли."
                )

            # 3. короткая история (обрезаем, чтобы не забивать контекст)
            if req.history:
                history_text = "\n".join(req.history[-10:])
                parts.append(
                    "ВЫДЕРЖКА ИЗ ПРОШЛОЙ ДИСКУССИИ (для справки, не подменяй исходный запрос):\n"
                    + history_text
                )

            # 4. ответы других ролей
            if ctx:
                for prev in order:
                    if prev in ctx:
                        parts.append(
                            f"Ответ {prev.upper()} (их мнение, не обязательно соглашаться):\n{ctx[prev]}"
                        )

            parts.append(
                "Отвечай кратко по своему формату, начиная с 1 строки, где ты перескажешь "
                "суть исходного запроса пользователя."
            )

            return "\n\n".join(parts)

        for agent in active_ordered:
            agent_input = build_agent_input(agent)
            text = ask_gigachat(agent, agent_input)
            ctx[agent] = text
            replies.append(AgentReply(agent=agent, text=text))
        if mode == "initial":
            summary_parts = [
                "ИСХОДНЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ (основа для всех выводов):\n"
                f"{user_msg}"
            ]
            for agent in order:
                if agent in ctx:
                    summary_parts.append(f"Ответ {agent.upper()}:\n{ctx[agent]}")
            if req.history:
                history_text = "\n".join(req.history[-20:])
                summary_parts.append(
                    "История обсуждения (последние 20 сообщений):\n"
                    + history_text
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
