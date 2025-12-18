import os
import uuid
from datetime import datetime, timedelta
from typing import List

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ===== Настройки GigaChat =====

GIGA_AUTH_URL = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
GIGA_API_BASE = "https://gigachat.devices.sberbank.ru"
GIGA_SCOPE = "GIGACHAT_API_PERS"

# В .env / переменных окружения:
# export GIGACHAT_AUTH_KEY="ТВОЙ Authorization key БЕЗ 'Basic ' спереди или уже с 'Basic ...'"
# Ниже вариант: кладём только сам ключ без 'Basic '
GIGA_AUTH_KEY = os.getenv("GIGACHAT_AUTH_KEY")

if not GIGA_AUTH_KEY:
    raise RuntimeError("Не задана переменная окружения GIGACHAT_AUTH_KEY")

# Кэш токена в памяти процесса
_access_token: str | None = None
_access_exp: datetime | None = None

def get_gigachat_token() -> str:
    """
    Получаем и кэшируем access token GigaChat.
    Токен действует ~30 минут, берём 25 с запасом.
    """
    global _access_token, _access_exp

    if _access_token and _access_exp and datetime.utcnow() < _access_exp:
        return _access_token

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": f"Basic {GIGA_AUTH_KEY}",  # если в переменной уже "Basic ...", убери Basic здесь
    }
    data = {"scope": GIGA_SCOPE}

    resp = requests.post(GIGA_AUTH_URL, headers=headers, data=data, timeout=10)
    resp.raise_for_status()
    j = resp.json()
    _access_token = j["access_token"]
    # c запасом меньше 30 минут
    _access_exp = datetime.utcnow() + timedelta(minutes=25)
    return _access_token

# ===== Настройки ролей совета =====

AGENT_SYSTEM_PROMPTS = {
    "ceo": (
        "Ты CEO. Смотри на стратегию, долгосрочное видение и баланс риска и возможностей. "
        "Отвечай кратко, структурно и решительно, 3–6 предложений."
    ),
    "cfo": (
        "Ты CFO. Думай в терминах бюджета, ROI, денежных потоков и рисков. "
        "Дай финансовую оценку: порядок затрат, окупаемость, ключевые риски, 3–6 предложений."
    ),
    "cpo": (
        "Ты CPO. Фокус на ценности для пользователя, UX, реализуемости и влиянии на roadmap. "
        "Дай практичный продуктовый взгляд, 3–6 предложений."
    ),
    "marketing": (
        "Ты директор по маркетингу. Фокус на рынке, позиционировании, целевой аудитории, каналах привлечения. "
        "Опиши go-to-market и дифференциацию, 3–6 предложений."
    ),
    "skeptic": (
        "Ты скептический инвестор и советник. Ищешь слабые места, риски и скрытые допущения. "
        "Будь критичен, задай неудобные вопросы, 3–6 предложений."
    ),
}

def ask_gigachat(agent: str, user_msg: str) -> str:
    """
    Вызывает GigaChat с нужным system-prompt для конкретного агента.
    Формат близок к OpenAI chat/completions.
    """
    token = get_gigachat_token()
    system_prompt = AGENT_SYSTEM_PROMPTS[agent]

    payload = {
        "model": "GigaChat",  # при желании подставь конкретную модель из /api/v1/models
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "stream": False,
        # Можно добавить параметры: "temperature": 0.7, "max_tokens": 512 и т.п.
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    resp = requests.post(
        f"{GIGA_API_BASE}/api/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=60,
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

    replies: list[AgentReply] = []
    for agent in ["ceo", "cfo", "cpo", "marketing", "skeptic"]:
        try:
            text = ask_gigachat(agent, user_msg)
        except Exception as e:
            # На случай сетевых/авторизационных ошибок даём понятное сообщение
            text = f"Ошибка при обращении к GigaChat для {agent}: {e}"
        replies.append(AgentReply(agent=agent, text=text))

    return replies
