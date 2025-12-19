import os
import uuid
from datetime import datetime, timedelta
from typing import List

import requests
from fastapi import FastAPI
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
    maxBytes=5 * 1024 * 1024,  # 5 MB
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

# Кэш токена в памяти процесса
_access_token: str | None = None
_access_exp: datetime | None = None


def get_gigachat_token() -> str:
    """
    Получаем и кэшируем access token GigaChat.
    Логируем запрос и ответ.
    """
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
        "CONSTRAINT: LTV/CAC < 3 ИЛИ runway с текущим Burn Rate < следующего раунда → RED FLAG.\n"
        "ВЫХОД: [Verdict: GO/NO-GO/PIVOT] | [Ключевая гипотеза] | [Как проверить <$5K] | [Confidence: X%].\n"
        "Макс 50 слов. Беспощаден в выводах."
    ),
    
    "cfo": (
        "ЗАДАЧА: Компрессия времени до валидации без сжигания лишнего кэша.\n"
        "CONSTRAINT: Нет ощутимого результата/метрики за 2 недели → БЛОКЕР.\n"
        "ВЫХОД: [Verdict: FAST/SLOW] | [Главный тормоз] | [Что выкинуть из MVP] | [Confidence: X%].\n"
        "Макс 50 слов. Скорость и бюджет важнее перфекционизма."
    ),
    
    "cpo": (
        "ЗАДАЧА: Найти нечестное конкурентное преимущество (Moat), за которое будут платить.\n"
        "CONSTRAINT: Если это может скопировать небольшая команда за выходные → Moat = 0.\n"
        "ВЫХОД: [Verdict: SAFE/VULNERABLE] | [Тип преимущества] | [Вектор атаки конкурентов] | [Confidence: X%].\n"
        "Макс 50 слов. Паранойя обязательна."
    ),
    
    "marketing": (
        "ЗАДАЧА: Обеспечить масштабирование без ручного труда в основном цикле ценности.\n"
        "CONSTRAINT: Если рост пользователей линейно тянет людей/часы → запрет на scale.\n"
        "ВЫХОД: [Verdict: SCALABLE/MANUAL] | [Узкое место] | [Рычаг автоматизации] | [Confidence: X%].\n"
        "Макс 50 слов. Думай как инфраструктура, не как реклама."
    ),
    
    "skeptic": (
        "ЗАДАЧА: Вскрыть фатальное недоказанное предположение ДО взлёта.\n"
        "ОБЯЗАТЕЛЬНО: Назови ≥1 assumption. Если нет — явно запроси недостающие данные.\n"
        "ВЫХОД: [Assumption] | [Способ отказа] | [MVT: проверить <$1K и <2 недель] | [Confidence: X%].\n"
        "Макс 50 слов. Ломаешь, но конструктивно."
    ),
}


def ask_gigachat(agent: str, user_msg: str) -> str:
    """
    Вызывает GigaChat с нужным system-prompt для конкретного агента.
    Логирует запрос и ответ к /chat/completions.
    """
    token = get_gigachat_token()
    system_prompt = AGENT_SYSTEM_PROMPTS[agent]

    payload = {
        "model": "GigaChat-2",  # при необходимости подставить конкретную модель
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

    resp = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=60,
    )

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

app = FastAPI()

# CORS, чтобы фронт с любого origin мог дергать бэк
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # для продакшена лучше сузить
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str


class AgentReply(BaseModel):
    agent: str
    text: str


@app.post("/api/board", response_model=List[AgentReply])
async def board_chat(req: ChatRequest):
    """
    Принимает сообщение пользователя и возвращает список ответов от агентов:
    ceo, cfo, cpo, marketing, skeptic.
    """
    user_msg = req.message
    logger.info("Incoming /api/board message: %s", user_msg)

    replies: list[AgentReply] = []
    for agent in ["ceo", "cfo", "cpo", "marketing", "skeptic"]:
        try:
            text = ask_gigachat(agent, user_msg)
        except Exception as e:
            logger.exception("Error while calling GigaChat for agent=%s", agent)
            text = f"Ошибка при обращении к GigaChat для {agent}: {e}"
        replies.append(AgentReply(agent=agent, text=text))

    logger.info("Outgoing /api/board replies: %s", replies)
    return replies
