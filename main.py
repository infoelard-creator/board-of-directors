import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Union
import hashlib
import json
import requests
from fastapi import FastAPI, Request, Depends
from auth import create_access_token, verify_token, TokenResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field  # ✅ Добавлен Field
import logging
from logging.handlers import RotatingFileHandler
from db import init_db, get_db, create_user_if_not_exists, User
from sqlalchemy.orm import Session
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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


def get_cached_compressed(user_id: str, message: str) -> Optional[dict]:
    """Получает кэшированное сжатое сообщение."""
    key = get_cache_key(user_id, message)
    return _compressed_cache.get(key)


def cache_compressed(user_id: str, message: str, compressed: dict) -> None:
    """Кэширует сжатое сообщение."""
    key = get_cache_key(user_id, message)
    _compressed_cache[key] = compressed
    if len(_compressed_cache) > 1000:
        keys_to_delete = list(_compressed_cache.keys())[:-500]
        for k in keys_to_delete:
            del _compressed_cache[k]
        logger.info("Compressed cache cleaned | remaining=%d", len(_compressed_cache))


def get_gigachat_token() -> str:
    """Получает или обновляет JWT токен доступа к GigaChat API."""
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
    "compressor": {"temperature": 0.2, "max_tokens": 150, "top_p": 0.85},
    "expander": {"temperature": 0.3, "max_tokens": 400, "top_p": 0.9},
}

# ===== ПРОМПТЫ СЖИМАТЕЛЯ И РАЗЖИМАТЕЛЯ =====

COMPRESSOR_SYSTEM_PROMPT = (
    "РОЛЬ: Компрессор. Сжимаешь текстовое сообщение пользователя в структурированную выжимку (JSON).\n"
    "ВЫХОД (ТОЛЬКО JSON, БЕЗ ТЕКСТА ВОКРУГ):\n"
    "{\n"
    "  \"intent\": \"одно из: validate_idea, find_risks, scale_strategy, compare_ideas, other\",\n"
    "  \"domain\": \"одно из: product, finance, marketing, strategy, operations, hr\",\n"
    "  \"idea_summary\": \"суть идеи в 1-2 предложениях (max 100 символов)\",\n"
    "  \"key_points\": [\"факт 1\", \"факт 2\", \"факт 3\"],\n"
    "  \"constraints\": {\"budget\": \"число или строка\", \"team\": \"число или строка\", \"timeline\": \"строка\"},\n"
    "  \"assumptions\": [\"предположение 1\", \"предположение 2\"],\n"
    "  \"key_facts\": [\"важный факт 1\", \"важный факт 2\"]\n"
    "}\n"
    "ТРЕБОВАНИЯ:\n"
    "- Не добавляй текст вне JSON\n"
    "- Сохраняй ТОЛЬКО критически важные детали\n"
    "- intent и domain: строго из предложенного списка\n"
    "- idea_summary: максимум 100 символов\n"
    "- key_points: 2-5 пунктов\n"
    "- constraints: только если упомянуты (иначе null)\n"
    "- assumptions: неявные предположения пользователя\n"
)

EXPANDER_SYSTEM_PROMPT = (
    "РОЛЬ: Экспандер (разжиматель). Преобразуешь сжатый JSON-ответ агента в читаемый текст.\n"
    "ВХОДНЫЕ ДАННЫЕ: сжатый JSON от агента.\n"
    "ВЫХОД: структурированный текст в СТРОГОМ ФОРМАТЕ (ОБЯЗАТЕЛЬНО!).\n"
    "\n"
    "ФОРМАТ ВЫВОДА (КРИТИЧЕН ДЛЯ ПАРСИНГА ФРОНТА):\n"
    "Каждая строка ДОЛЖНА быть в формате: [Label] — значение\n"
    "Примеры:\n"
    "[Verdict] — GO\n"
    "[Confidence] — 87%\n"
    "[Key Strategy] — основная идея стратегии\n"
    "[Budget] — 50000 USD\n"
    "[Timeline] — 12 недель\n"
    "[Risk 1] — первый риск\n"
    "[Risk 2] — второй риск\n"
    "\n"
    "СТРОГИЕ ТРЕБОВАНИЯ:\n"
    "1. НИКАКИХ абзацев, только строки в формате [Label] — значение\n"
    "2. НИКАКИХ пустых строк между записями\n"
    "3. Если в JSON есть массив (risk[], points[] и т.д.) — каждый элемент на отдельной строке с тем же label:\n"
    "   [Risk] — риск 1\n"
    "   [Risk] — риск 2\n"
    "   [Risk] — риск 3\n"
    "4. Числа ВСЕГДА в квадратных скобках: [Confidence] — 85%\n"
    "5. Вердикты в квадратных скобках: [Verdict] — GO (или NO-GO, SAFE, FAST и т.д.)\n"
    "6. НЕ добавляй никакой текст вне формата [Label] — значение\n"
    "7. НЕ добавляй информацию, которой нет в JSON\n"
    "8. Сохраняй все цифры, проценты и ключевые идеи из JSON ДА БУКВА\n"
    "9. Пиши естественно, но точно следуй источнику\n"
    "10. МАКСИМУМ 15 строк (лаконично!)\n"
)


# ===== ПРОМПТЫ АГЕНТОВ В НОВОМ СЖАТОМ ФОРМАТЕ =====

AGENT_SYSTEM_PROMPTS = {
    "ceo": (
        "РОЛЬ: CEO. Анализируешь СЖАТУЮ выжимку идеи.\n"
        "ВХОДНЫЕ ДАННЫЕ: JSON с intent, domain, idea_summary, constraints и т.д.\n"
        "ВЫХОД ТОЛЬКО В ВИДЕ JSON (БЕЗ ТЕКСТА ВОКРУГ):\n"
        "{\n"
        "  \"verdict\": \"GO или NO-GO\",\n"
        "  \"confidence\": число 0-100,\n"
        "  \"key_strategy\": \"главная стратегическая идея (1-2 предложения)\",\n"
        "  \"ltv_considerations\": \"ключевые факторы LTV/CAC (1-2 предложения)\",\n"
        "  \"risks\": [\"риск 1\", \"риск 2\"],\n"
        "  \"next_steps\": [\"шаг 1 для проверки\", \"шаг 2 для проверки\"]\n"
        "}\n"
        "ТРЕБОВАНИЯ:\n"
        "- verdict: строго GO или NO-GO\n"
        "- confidence: число от 0 до 100\n"
        "- Фокусируйся на LTV/CAC, runway и стратегии роста\n"
        "- НЕ добавляй текст вне JSON\n"
    ),
    "cfo": (
        "РОЛЬ: CFO. Оцениваешь финансовую валидацию на основе СЖАТОЙ выжимки.\n"
        "ВХОДНЫЕ ДАННЫЕ: JSON с идеей, бюджетом, ограничениями.\n"
        "ВЫХОД ТОЛЬКО В ВИДЕ JSON (БЕЗ ТЕКСТА ВОКРУГ):\n"
        "{\n"
        "  \"verdict\": \"FAST или SLOW\",\n"
        "  \"confidence\": число 0-100,\n"
        "  \"budget_estimate\": \"минимальный бюджет в USD (число или диапазон)\",\n"
        "  \"validation_hypothesis\": \"что нужно проверить за деньги (1 предложение)\",\n"
        "  \"timeline\": \"сроки для 80% валидации (в неделях)\",\n"
        "  \"roi_considerations\": [\"фактор ROI 1\", \"фактор ROI 2\"]\n"
        "}\n"
        "ТРЕБОВАНИЯ:\n"
        "- verdict: строго FAST или SLOW\n"
        "- budget_estimate: число в USD\n"
        "- timeline: число недель\n"
        "- Ищи метрику, валидируемую дёшево и быстро\n"
        "- НЕ добавляй текст вне JSON\n"
    ),
    "cpo": (
        "РОЛЬ: CPO. Ищешь конкурентный дефицит (Moat) на основе СЖАТОЙ выжимки.\n"
        "ВХОДНЫЕ ДАННЫЕ: JSON с идеей, domain, ограничениями.\n"
        "ВЫХОД ТОЛЬКО В ВИДЕ JSON (БЕЗ ТЕКСТА ВОКРУГ):\n"
        "{\n"
        "  \"verdict\": \"SAFE или VULNERABLE\",\n"
        "  \"confidence\": число 0-100,\n"
        "  \"moat_assessment\": \"что сложно скопировать и почему (1-2 предложения)\",\n"
        "  \"competitive_risks\": [\"конкурент 1 или угроза 1\", \"конкурент 2 или угроза 2\"],\n"
        "  \"differentiation\": \"ключевая отличие от конкурентов (1 предложение)\",\n"
        "  \"defensibility_timeline\": \"сколько недель до копирования конкурентами\"\n"
        "}\n"
        "ТРЕБОВАНИЯ:\n"
        "- verdict: строго SAFE или VULNERABLE\n"
        "- confidence: число от 0 до 100\n"
        "- defensibility_timeline: число недель\n"
        "- Опирайся на конкретные функции, не абстракции\n"
        "- НЕ добавляй текст вне JSON\n"
    ),
    "marketing": (
        "РОЛЬ: VP Marketing. Придумываешь канал роста на основе СЖАТОЙ выжимки.\n"
        "ВХОДНЫЕ ДАННЫЕ: JSON с идеей, domain, constraints.\n"
        "ВЫХОД ТОЛЬКО В ВИДЕ JSON (БЕЗ ТЕКСТА ВОКРУГ):\n"
        "{\n"
        "  \"verdict\": \"SCALABLE или MANUAL\",\n"
        "  \"confidence\": число 0-100,\n"
        "  \"target_audience\": \"целевая аудитория (1 предложение)\",\n"
        "  \"growth_hack\": \"конкретный гроуз-хак, механика (1-2 предложения)\",\n"
        "  \"channel\": \"основной канал для первых 100 клиентов\",\n"
        "  \"unit_economics\": \"примерные CAC и LTV в идеальном сценарии\",\n"
        "  \"scalability_bottleneck\": \"основное ограничение масштабирования\"\n"
        "}\n"
        "ТРЕБОВАНИЯ:\n"
        "- verdict: строго SCALABLE или MANUAL\n"
        "- confidence: число от 0 до 100\n"
        "- growth_hack: конкретная механика, не общие фразы\n"
        "- Предложи то, что работает БЕЗ найма людей на начальном этапе\n"
        "- НЕ добавляй текст вне JSON\n"
    ),
    "skeptic": (
        "РОЛЬ: Skeptic. Находишь фатальные дыры на основе СЖАТОЙ выжимки.\n"
        "ВХОДНЫЕ ДАННЫЕ: JSON с идеей и её деталями.\n"
        "ВЫХОД ТОЛЬКО В ВИДЕ JSON (БЕЗ ТЕКСТА ВОКРУГ):\n"
        "{\n"
        "  \"verdict\": \"FATAL или FIXABLE\",\n"
        "  \"confidence\": число 0-100,\n"
        "  \"fatal_flaw\": \"самое уязвимое утверждение в идее (1-2 предложения)\",\n"
        "  \"crash_test\": \"как убить эту идею дёшево (<$1K) за 2 недели\",\n"
        "  \"attack_vectors\": [\"способ атаки 1\", \"способ атаки 2\", \"способ атаки 3\"],\n"
        "  \"counter_arguments\": [\"возможный контраргумент 1\", \"возможный контраргумент 2\"]\n"
        "}\n"
        "ТРЕБОВАНИЯ:\n"
        "- verdict: строго FATAL или FIXABLE\n"
        "- confidence: число от 0 до 100\n"
        "- Атакуй конкретные утверждения, не общие критики\n"
        "- crash_test: должно быть дёшево и быстро\n"
        "- НЕ добавляй текст вне JSON\n"
    ),
    "summary": (
        "РОЛЬ: Модератор. Синтезируешь СЖАТЫЕ мнения совета.\n"
        "ВХОДНЫЕ ДАННЫЕ: JSON выжимки от всех агентов (CEO, CFO, CPO, Marketing, Skeptic).\n"
        "ВЫХОД ТОЛЬКО В ВИДЕ JSON (БЕЗ ТЕКСТА ВОКРУГ):\n"
        "{\n"
        "  \"idea_essence\": \"суть идеи в 1-2 предложениях\",\n"
        "  \"overall_verdict\": \"GO, CONDITIONAL_GO, NO-GO\",\n"
        "  \"overall_confidence\": число 0-100,\n"
        "  \"consensus_points\": [\"точка согласия 1\", \"точка согласия 2\"],\n"
        "  \"disagreements\": [\"точка разногласия 1\"],\n"
        "  \"key_risks\": [\"главный риск 1\", \"главный риск 2\"],\n"
        "  \"next_validation_step\": \"первый шаг для проверки идеи\",\n"
        "  \"board_reasoning\": \"краткое обоснование вердикта совета (1-2 предложения)\"\n"
        "}\n"
        "ТРЕБОВАНИЯ:\n"
        "- overall_verdict: GO, CONDITIONAL_GO или NO-GO\n"
        "- overall_confidence: число от 0 до 100\n"
        "- Синтезируй мнения всех членов совета\n"
        "- Выяви точки согласия и разногласия\n"
        "- НЕ добавляй текст вне JSON\n"
    ),
}

# ===== ПАРСЕР ИСХОДНОГО ЗАПРОСА =====

PARSER_SYSTEM_PROMPT = (
    "РОЛЬ: Parser. Структурируешь исходный запрос пользователя.\n"
    "ВЫХОД (JSON, строго в этом формате):\n"
    "{\n"
    "  \"intent\": \"validate_idea|find_risks|scale_strategy|compare_ideas|other\",\n"
    "  \"domain\": \"product|finance|marketing|strategy|operations|hr\",\n"
    "  \"key_points\": [\"точка 1\", \"точка 2\"],\n"
    "  \"assumptions\": [\"предположение 1\"],\n"
    "  \"constraints\": [\"ограничение 1\"],\n"
    "  \"summary\": \"одно предложение о сути запроса\"\n"
    "}\n"
    "Требования:\n"
    "- intent: конкретная цель пользователя\n"
    "- domain: один из списка\n"
    "- key_points: 2-5 главных утверждений\n"
    "- assumptions: что неявно предполагает пользователь\n"
    "- constraints: бюджет, сроки, команда, ресурсы\n"
    "- summary: суть в 1 строке\n"
    "Отвечай ТОЛЬКО JSON, без комментариев."
)


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


class AgentReply(BaseModel):
    """Ответ агента (совместимо с фронтом)."""
    agent: str
    text: str
    compressed: Optional[dict] = None


class AgentReplyWithDebug(BaseModel):
    """Ответ агента с обязательным сжатым полем."""
    agent: str
    text: str
    compressed: dict


class ChatResponseDebug(BaseModel):
    """Расширенный ответ с полной отладочной информацией."""
    user_message_original: str
    user_message_compressed: dict
    agents_replies: List[AgentReplyWithDebug]


class SingleAgentRequest(BaseModel):
    """Запрос для одного агента."""
    agent: str
    message: Optional[str] = None
    history: Optional[List[str]] = None
    debug: Optional[bool] = False


class SingleAgentReply(BaseModel):
    """Ответ одного агента."""
    text: str
    compressed: Optional[dict] = None


class SummaryRequest(BaseModel):
    """Запрос пересчёта итогов."""
    history: Optional[List[str]] = None
    debug: Optional[bool] = False


class SummaryReply(BaseModel):
    """Ответ пересчёта итогов."""
    text: str
    compressed: Optional[dict] = None


class LoginRequest(BaseModel):
    """Запрос логина."""
    user_id: str = Field(
        ..., 
        min_length=1, 
        max_length=255, 
        pattern="^[a-zA-Z0-9_-]+$",
        description="User ID (буквы, цифры, подчёркивание, дефис)"
    )


# ===== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====

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
        
        # Проверка что JSON не пустой и содержит обязательные поля
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


def expand_agent_output(agent: str, compressed_output: dict) -> str:
    """Разворачивает сжатый JSON-ответ агента в читаемый текст."""
    token = get_gigachat_token()

    agent_context = f"Агент: {agent.upper()}\n"

    payload = {
        "model": "GigaChat-2",
        "messages": [
            {"role": "system", "content": EXPANDER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"{agent_context}Вот сжатый ответ (JSON), разверни в естественный текст:\n\n{json.dumps(compressed_output, ensure_ascii=False, indent=2)}"
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

    logger.info(
        "Expander request -> %s | agent=%s",
        url,
        agent,
    )

    resp = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)
    resp.raise_for_status()

    j = resp.json()
    expanded_text = j["choices"][0]["message"]["content"].strip()

    logger.info(
        "Expander response <- %s | agent=%s | text_len=%d",
        url,
        agent,
        len(expanded_text),
    )

    return expanded_text


def compress_history(history: Optional[List[str]], max_items: int = 15) -> str:
    """Сжимает историю до последних N сообщений для экономии токенов."""
    if not history:
        return ""
    recent = history[-max_items:]
    return "\n".join(recent)


def ask_gigachat(agent: str, user_msg: str) -> str:
    """Запрос к GigaChat с оптимизированными параметрами."""
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

    resp = requests.post(url, headers=headers, json=payload, timeout=60, verify=False)

    logger.info(
        "Chat response <- %s | agent=%s | status=%s",
        url,
        agent,
        resp.status_code,
    )

    resp.raise_for_status()
    j = resp.json()
    return j["choices"][0]["message"]["content"].strip()


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
    """Логин: принимает user_id, создаёт пользователя, возвращает JWT."""
    create_user_if_not_exists(db, body.user_id)
    token = create_access_token(body.user_id)
    return TokenResponse(access_token=token)


@app.post("/api/board")
@limiter.limit("10/minute")
async def board_chat(
    req: ChatRequest,
    request: Request,
    user_id: str = Depends(verify_token),
) -> Union[List[AgentReply], Dict]:
    """
    Оптимизированная версия board_chat с компрессией.
    1. Сжимаем исходный запрос пользователя
    2. Все агенты получают СЖАТУЮ выжимку и отвечают в СЖАТОМ формате
    3. Разжимаем ответы для пользователя
    4. Возвращаем: разжатый текст для UI + (опционально) сжатую версию для отладки
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

    # Шаг 1: Сжимаем исходное сообщение пользователя
    compressed_user_msg = compress_user_message(user_msg, user_id=user_id)
    logger.info(
        "Compressed user message | intent=%s | domain=%s | idea_summary=%s",
        compressed_user_msg.intent,
        compressed_user_msg.domain,
        compressed_user_msg.idea_summary,
    )

    replies: List[AgentReply] = []
    ctx: dict[str, dict] = {}  # Хранит СЖАТЫЕ ответы (dict)

    try:
        # Шаг 2: Обрабатываем каждого агента
        for agent in active_ordered:
            # Строим контекст из сжатых данных
            parts: List[str] = [
                "СЖАТЫЙ ЗАПРОС ПОЛЬЗОВАТЕЛЯ (JSON):",
                json.dumps(compressed_user_msg.dict(), ensure_ascii=False, indent=2),
            ]

            # Добавляем сжатые мнения предыдущих агентов
            if ctx:
                parts.append("\nСЖАТЫЕ МНЕНИЯ ДРУГИХ ЧЛЕНОВ СОВЕТА (JSON):")
                for prev_agent in order:
                    if prev_agent in ctx:
                        parts.append(f"{prev_agent}:")
                        parts.append(json.dumps(ctx[prev_agent], ensure_ascii=False, indent=2))

            # Добавляем историю (сжатую)
            compressed = compress_history(req.history, max_items=5)
            if compressed:
                parts.append("\nВЫДЕЖКА ИЗ ИСТОРИИ (последние 5 сообщений):")
                parts.append(compressed)

            agent_input = "\n".join(parts)

            # Получаем СЖАТЫЙ ответ от агента
            raw_response = ask_gigachat(agent, agent_input)

            # Парсим JSON ответ
            try:
                compressed_response = json.loads(raw_response)
                logger.info(
                    "Agent %s returned valid JSON | verdict=%s",
                    agent,
                    compressed_response.get("verdict", "N/A"),
                )
            except json.JSONDecodeError:
                logger.warning("Agent %s returned non-JSON response: %s", agent, raw_response)
                compressed_response = {
                    "verdict": "NO-DATA",
                    "confidence": 0,
                    "raw_response": raw_response
                }

            # Сохраняем сжатый ответ для следующих агентов
            ctx[agent] = compressed_response

            # Разжимаем для фронта
            expanded_text = expand_agent_output(agent, compressed_response)

            # Возвращаем: разжатый текст + опционально сжатый (для отладки)
            reply = AgentReply(
                agent=agent,
                text=expanded_text,
                compressed=compressed_response if debug else None
            )
            replies.append(reply)

        # Шаг 3: Summary агент (если mode="initial")
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
                    summary_parts.append(json.dumps(ctx[agent], ensure_ascii=False, indent=2))

            summary_input = "\n".join(summary_parts)

            raw_summary = ask_gigachat("summary", summary_input)

            try:
                compressed_summary = json.loads(raw_summary)
            except json.JSONDecodeError:
                logger.warning("Summary agent returned non-JSON: %s", raw_summary)
                compressed_summary = {"overall_verdict": "NO-DATA", "raw_response": raw_summary}

            expanded_summary = expand_agent_output("summary", compressed_summary)

            reply = AgentReply(
                agent="summary",
                text=expanded_summary,
                compressed=compressed_summary if debug else None
            )
            replies.append(reply)

    except Exception as e:
        logger.exception("Error while calling GigaChat board chain | user=%s", user_id)
        replies.append(
            AgentReply(agent="error", text=f"Ошибка при обращении к GigaChat: {e}")
        )

    logger.info(
        "Outgoing /api/board | agents=%s | reply_count=%d | debug=%s",
        active_ordered,
        len(replies),
        debug,
    )

    # Если debug=True, возвращаем расширенный ответ с отладкой
    if debug:
        valid_replies = [r for r in replies if r.agent != "error"]
        return ChatResponseDebug(
            user_message_original=user_msg,
            user_message_compressed=compressed_user_msg.dict(),
            agents_replies=[
                AgentReplyWithDebug(
                    agent=r.agent,
                    text=r.text,
                    compressed=r.compressed or {}
                )
                for r in valid_replies
            ]
        ).dict()

    # Иначе возвращаем обычный список AgentReply (обратная совместимость)
    return replies


@app.post("/api/agent", response_model=SingleAgentReply)
@limiter.limit("20/minute")
async def single_agent(
    req: SingleAgentRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):
    """Одиночный агент с компрессией."""
    logger.info(
        "Incoming /api/agent: agent=%s | message=%s | user=%s | debug=%s",
        req.agent,
        (req.message or "")[:50] if req.message else "None",
        user_id,
        req.debug,
    )

    if req.agent not in AGENT_SYSTEM_PROMPTS:
        return SingleAgentReply(text=f"Неизвестный агент: {req.agent}")

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
        raw_response = ask_gigachat(req.agent, full_content)

        try:
            compressed_response = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Agent %s returned non-JSON: %s", req.agent, raw_response)
            compressed_response = {"raw_response": raw_response}

        expanded_text = expand_agent_output(req.agent, compressed_response)

        return SingleAgentReply(
            text=expanded_text,
            compressed=compressed_response if req.debug else None
        )
    except Exception as e:
        logger.exception("Error in /api/agent | agent=%s | user=%s", req.agent, user_id)
        return SingleAgentReply(
            text=f"Ошибка при обращении к GigaChat для агента {req.agent}: {e}"
        )


@app.post("/api/summary", response_model=SummaryReply)
@limiter.limit("10/minute")
async def recalc_summary(
    req: SummaryRequest,
    request: Request,
    user_id: str = Depends(verify_token),
):
    """Пересчёт итогов на основе последней истории обсуждения."""
    logger.info(
        "Incoming /api/summary | history_len=%s | user=%s | debug=%s",
        len(req.history) if req.history else 0,
        user_id,
        req.debug,
    )

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
        raw_response = ask_gigachat("summary", summary_input)

        try:
            compressed_response = json.loads(raw_response)
        except json.JSONDecodeError:
            logger.warning("Summary returned non-JSON: %s", raw_response)
            compressed_response = {"raw_response": raw_response}

        expanded_text = expand_agent_output("summary", compressed_response)

        return SummaryReply(
            text=expanded_text,
            compressed=compressed_response if req.debug else None
        )
    except Exception as e:
        logger.exception("Error in /api/summary | user=%s", user_id)
        return SummaryReply(
            text=f"Ошибка при обращении к GigaChat для пересчёта итогов: {e}"
        )
