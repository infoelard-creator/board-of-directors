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
    Принимает сообщение пользователя и возвращает список ответов от агентов
    ceo, cfo, cpo, marketing, skeptic, которые отвечают последовательно,
    учитывая ответы друг друга.
    """
    user_msg = req.message
    logger.info("Incoming /api/board message: %s", user_msg)

    replies: list[AgentReply] = []

    try:
        # CEO
        ceo_input = f"Запрос пользователя:\n{user_msg}"
        ceo_text = ask_gigachat("ceo", ceo_input)
        replies.append(AgentReply(agent="ceo", text=ceo_text))

        # CFO
        cfo_input = (
            f"Запрос пользователя:\n{user_msg}\n\n"
            f"Ответ CEO:\n{ceo_text}"
        )
        cfo_text = ask_gigachat("cfo", cfo_input)
        replies.append(AgentReply(agent="cfo", text=cfo_text))

        # CPO
        cpo_input = (
            f"Запрос пользователя:\n{user_msg}\n\n"
            f"Ответ CEO:\n{ceo_text}\n\n"
            f"Ответ CFO:\n{cfo_text}"
        )
        cpo_text = ask_gigachat("cpo", cpo_input)
        replies.append(AgentReply(agent="cpo", text=cpo_text))

        # Marketing
        marketing_input = (
            f"Запрос пользователя:\n{user_msg}\n\n"
            f"Ответ CEO:\n{ceo_text}\n\n"
            f"Ответ CFO:\n{cfo_text}\n\n"
            f"Ответ CPO:\n{cpo_text}"
        )
        marketing_text = ask_gigachat("marketing", marketing_input)
        replies.append(AgentReply(agent="marketing", text=marketing_text))

        # Skeptic
        skeptic_input = (
            f"Запрос пользователя:\n{user_msg}\n\n"
            f"Ответ CEO:\n{ceo_text}\n\n"
            f"Ответ CFO:\n{cfo_text}\n\n"
            f"Ответ CPO:\n{cpo_text}\n\n"
            f"Ответ маркетинга:\n{marketing_text}"
        )
        skeptic_text = ask_gigachat("skeptic", skeptic_input)
        replies.append(AgentReply(agent="skeptic", text=skeptic_text))

    except Exception as e:
        logger.exception("Error while calling GigaChat board chain")
        # если что-то падает посреди цепочки — уже собранные ответы вернём,
        # а для упавшей/следующих ролей можно добавить заглушку
        replies.append(AgentReply(agent="error", text=f"Ошибка при обращении к GigaChat: {e}"))

    logger.info("Outgoing /api/board replies: %s", replies)
    return replies
