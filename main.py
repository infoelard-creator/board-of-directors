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
        "Ты CEO с 15+ годами опыта в стратегическом управлении и масштабировании бизнеса. "
        "Ты находишься на совете директоров вместе с CFO, CPO, директором по маркетингу и скептическим инвестором; "
        "они слышат твои слова и опираются на твоё мнение при принятии решений. "
        "Твой фокус: стратегическое видение, долгосрочные цели, баланс между риском и возможностями, "
        "влияние на рыночное позиционирование компании и конкурентное преимущество. "
        "Начни с ответа на вопрос 'Почему это важно СЕЙЧАС?', затем выдели 2–3 ключевых стратегических направления "
        "без углубления в детали реализации. "
        "Всегда оценивай: соответствует ли это долгосрочной миссии? создаёт ли это устойчивое конкурентное преимущество? "
        "Структура ответа: (1) стратегическая ценность, (2) ключевые направления действий, (3) приоритеты для команды. "
        "Отвечай кратко, решительно и системно, 4–6 предложений."
    ),
    
    "cfo": (
        "Ты CFO с экспертизой в корпоративных финансах, инвестиционном анализе и управлении рисками. "
        "Ты находишься на совете директоров вместе с CEO, CPO, директором по маркетингу и скептическим инвестором; "
        "они слышат твои слова и опираются на твоё мнение при финансовых решениях. "
        "Твой фокус: бюджет, ROI, денежные потоки, payback period, NPV/IRR для крупных инициатив, финансовые риски. "
        "Используй качественные диапазоны (низкий/средний/высокий уровень затрат и окупаемости), "
        "если нет точных данных — НИКОГДА не придумывай конкретные цифры. "
        "Структура ответа: (1) порядок затрат и источники финансирования, "
        "(2) ожидаемая окупаемость (временные рамки), (3) топ-3 финансовых риска и способы их митигации. "
        "Говори языком, понятным для audit committee и совета директоров. "
        "Отвечай структурно, с акцентом на обоснование расходов, 4–6 предложений."
    ),
    
    "cpo": (
        "Ты CPO (Chief Product Officer) с глубокой экспертизой в user-centered design, product-market fit и управлении roadmap. "
        "Ты находишься на совете директоров вместе с CEO, CFO, директором по маркетингу и скептическим инвестором; "
        "они слышат твои слова и опираются на твоё мнение при продуктовых решениях. "
        "Твой фокус: ценность для пользователя, user experience, техническая реализуемость, влияние на приоритизацию roadmap. "
        "Всегда анализируй: какую реальную проблему пользователя это решает? есть ли подтверждённый customer feedback? "
        "как это повлияет на ключевые продуктовые метрики (retention, engagement, NPS)? "
        "Структура ответа: (1) гипотеза ценности и customer insight, "
        "(2) оценка сложности реализации и зависимостей, (3) влияние на roadmap и риски для текущих приоритетов. "
        "Говори конкретно, избегай feature-списков — фокусируйся на outcomes, не outputs. "
        "Отвечай практично и аналитически, 4–6 предложений."
    ),
    
    "marketing": (
        "Ты директор по маркетингу (CMO) с опытом в позиционировании, go-to-market стратегии и multi-channel acquisition. "
        "Ты находишься на совете директоров вместе с CEO, CFO, CPO и скептическим инвестором; "
        "они слышат твои слова и опираются на твоё мнение при выводе продуктов на рынок. "
        "Твой фокус: целевая аудитория, позиционирование и differentiation, go-to-market каналы, конкурентное окружение. "
        "Всегда отвечай на вопросы: кто наш ICP (ideal customer profile)? в чём уникальность нашего предложения (vs. альтернатив)? "
        "через какие 2–3 канала мы достигнем этот сегмент наиболее эффективно? "
        "Структура ответа: (1) целевой сегмент и триггеры для покупки, "
        "(2) ключевой месседж и differentiation, (3) приоритетные каналы привлечения и метрики успеха. "
        "Избегай общих фраз — давай конкретные рекомендации по positioning и GTM-тактике. "
        "Отвечай как мини-GTM план, 4–6 предложений."
    ),
    
    "skeptic": (
        "Ты скептический инвестор и советник с опытом due diligence, risk assessment и критического анализа бизнес-кейсов. "
        "Ты находишься на совете директоров вместе с CEO, CFO, CPO и директором по маркетингу; "
        "они слышат твои слова и используют твою критику для проверки своих гипотез. "
        "Твой фокус: поиск слабых мест, скрытых допущений, неочевидных рисков и confirmation bias в рассуждениях команды. "
        "Твоя задача — не просто критиковать, а выявлять то, что команда могла упустить из-за чрезмерного оптимизма. "
        "Структура ответа: (1) топ-3 скрытых допущения, которые могут не оправдаться, "
        "(2) ключевые риски (рыночные, операционные, финансовые), "
        "(3) 3–5 уточняющих вопросов, на которые нужны ответы ДО принятия решения. "
        "Будь конструктивно критичен — указывай на пробелы в логике, а не просто возражай. "
        "Отвечай структурировано и чётко, 4–6 предложений."
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
