# 🧪 TESTING GUIDE — Board.AI (Clarity Feedback Loop)

**Дата:** 09.01.2026  
**Версия приложения:** 1.0.0  
**Слои реализованы:** Слой 1 "Терапевт" + Слой 2 "Совет директоров"  
**Последнее обновление конфига:** `.env` (легаси `.env.example` больше не используется)

---

## 📋 СОДЕРЖАНИЕ

1. [Подготовка окружения](#подготовка-окружения)
2. [Запуск бэкенда](#запуск-бэкенда)
3. [Получение JWT токенов](#получение-jwt-токенов)
4. [API Testing Reference](#api-testing-reference)
5. [Интеграционные тесты](#интеграционные-тесты)
6. [Тестирование фронтенда](#тестирование-фронтенда)
7. [Troubleshooting](#troubleshooting)

---

## 🚀 Подготовка окружения

### Шаг 1: Клонировать репозиторий (если нужно)

\`\`\`bash
cd /workspaces/board-of-directors
\`\`\`

### Шаг 2: Проверить наличие Virtual Environment

\`\`\`bash
# Проверяем, есть ли venv
ls -la venv/

# Если venv не существует, создаём его
python3 -m venv venv

# Активируем venv
source venv/bin/activate

# На Windows:
# venv\Scripts\activate
\`\`\`

### Шаг 3: Установить зависимости

\`\`\`bash
# Убеждаемся, что venv активирован (должен быть префикс (venv))
pip install --upgrade pip

# Устанавливаем зависимости
pip install -r requirements.txt

# Проверяем установку
pip list | grep -E "fastapi|sqlalchemy|python-jose|pytest"
\`\`\`

**Ожидаемый вывод:**
\`\`\`
fastapi                 0.104.1
sqlalchemy              2.0.23
python-jose             3.3.0
pytest                  7.4.3
...
\`\`\`

### Шаг 4: Проверить переменные окружения (.env)

\`\`\`bash
# Проверяем, что .env существует и содержит необходимые переменные
cat /workspaces/board-of-directors/.env

# Должны быть:
# GIGACHAT_AUTH_KEY=...
# JWT_SECRET_KEY=...
# DATABASE_URL=sqlite:///./test.db
\`\`\`

**Если .env отсутствует:**

\`\`\`bash
# Создаём новый .env файл с нужными переменными
cat > .env << 'ENVEOF'
# GigaChat API Key
GIGACHAT_AUTH_KEY=your_gigachat_key_here

# JWT Configuration
JWT_SECRET_KEY=your_secret_key_here_min_32_chars

# Database
DATABASE_URL=sqlite:///./test.db
ENVEOF

# Редактируем:
nano .env
# или
code .env
\`\`\`

**⚠️ ВАЖНО:** Переменные в `.env` **больше не генерируются из `run_backend.sh`** — всё управляется через `.env` файл!

---

## 🔌 Запуск бэкенда

### Способ 1: Запуск через Python (рекомендуется)

\`\`\`bash
# Активируем venv
source venv/bin/activate

# Запускаем приложение (с auto-reload при изменении файлов)
python3 main.py
\`\`\`

**Ожидаемый вывод:**
\`\`\`
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete
INFO:     Database initialized
...
\`\`\`

### Способ 2: Прямой запуск через uvicorn

\`\`\`bash
# Если хотите явно управлять параметрами
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
\`\`\`

### Проверить здоровье приложения

\`\`\`bash
# Health check endpoint
curl http://localhost:8000/health

# Ожидаемый ответ:
# {"status":"ok","service":"board-ai"}
\`\`\`

---

## 🔐 Получение JWT токенов

### 1️⃣ Логин (получить access + refresh токены)

**Endpoint:** \`POST /api/login\`

**Пример с curl:**

\`\`\`bash
curl -X POST http://localhost:8000/api/login \\
  -H "Content-Type: application/json" \\
  -d '{"user_id": "test_user_001"}'
\`\`\`

**Ожидаемый ответ (200 OK):**

\`\`\`json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdF91c2VyXzAwMSIsInRva2VuX3R5cGUiOiJhY2Nlc3MiLCJleHAiOjE3MDI1NTU3NTN9.7X1...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdF91c2VyXzAwMSIsInRva2VuX3R5cGUiOiJyZWZyZXNoIiwiZXhwIjoxNzA1NTUzNzUzfQ.1y8...",
  "token_type": "bearer",
  "expires_in": 900
}
\`\`\`

**Что означают поля:**
- \`access_token\` — токен для API запросов (действует 15 минут = 900 секунд)
- \`refresh_token\` — токен для получения нового access_token (действует 30 дней)
- \`token_type\` — всегда "bearer"
- \`expires_in\` — время жизни access_token в секундах

---

### 2️⃣ Использование токена в запросах (Bearer Token)

**Сохраняем токены в переменные:**

\`\`\`bash
# Первый логин — получаем оба токена
LOGIN_RESPONSE=\$(curl -s -X POST http://localhost:8000/api/login \\
  -H "Content-Type: application/json" \\
  -d '{"user_id": "test_user_001"}')

# Сохраняем токены
ACCESS_TOKEN=\$(echo \$LOGIN_RESPONSE | jq -r '.access_token')
REFRESH_TOKEN=\$(echo \$LOGIN_RESPONSE | jq -r '.refresh_token')

echo "Access Token: \$ACCESS_TOKEN"
echo "Refresh Token: \$REFRESH_TOKEN"
\`\`\`

**Проверяем, что токены получены:**

\`\`\`bash
# Должны вывести что-то вроде:
# Access Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo...
# Refresh Token: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjo...
\`\`\`

---

### 3️⃣ Рефреш токена (когда access_token истекает)

**Endpoint:** \`POST /api/refresh\`

**Пример с curl:**

\`\`\`bash
curl -X POST http://localhost:8000/api/refresh \\
  -H "Content-Type: application/json" \\
  -d "{\"refresh_token\": \"\$REFRESH_TOKEN\"}"
\`\`\`

**Ожидаемый ответ (200 OK):**

\`\`\`json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoidGVzdF91c2VyXzAwMSIsInRva2VuX3R5cGUiOiJhY2Nlc3MiLCJleHAiOjE3MDI1NTU4NTN9.9X2...",
  "token_type": "bearer",
  "expires_in": 900
}
\`\`\`

**Что делать:**
- Сохраняем новый \`access_token\`
- \`refresh_token\` остается прежним (не меняется)
- Использум новый \`access_token\` для следующих запросов

---

## 🔌 API Testing Reference

### Структура всех запросов с авторизацией

**Все endpoints (кроме /login) требуют Authorization header:**

\`\`\`bash
Authorization: Bearer <access_token>
\`\`\`

**Пример:**

\`\`\`bash
curl -X POST http://localhost:8000/api/board \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$ACCESS_TOKEN" \\
  -d '{...}'
\`\`\`

---

### Endpoint 1: Чат с Советом директоров

**Endpoint:** \`POST /api/board\`

**Назначение:** Основной чат с множеством агентов (CFO, CPO, CEO, CTO и т.д.)

**Тело запроса (Request):**

\`\`\`json
{
  "message": "У нас проблема с retention клиентов. Нужно срочно поднять NPS.",
  "active_agents": ["cfo", "cpo", "cto"],
  "history": [],
  "mode": "initial",
  "debug": false
}
\`\`\`

**Поля:**
- \`message\` (string, обязательно) — сообщение пользователя
- \`active_agents\` (array, опционально) — какие агенты должны ответить (по умолчанию все)
- \`history\` (array, опционально) — история предыдущих сообщений для контекста
- \`mode\` (string, опционально) — "initial" (новый запрос) или "refresh" (пересчёт итогов)
- \`debug\` (boolean, опционально) — включить ли отладочную информацию

**Пример curl:**

\`\`\`bash
curl -X POST http://localhost:8000/api/board \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$ACCESS_TOKEN" \\
  -d '{
    "message": "Нужно оптимизировать Cloud costs",
    "active_agents": ["cfo", "cto"],
    "mode": "initial",
    "debug": true
  }'
\`\`\`

**Ожидаемый ответ (200 OK):**

\`\`\`json
{
  "agents": [
    {
      "name": "CFO",
      "role": "Chief Financial Officer",
      "response": "С точки зрения финансов, Cloud затраты составляют ~15% от бюджета IT...",
      "recommendations": [
        "Перейти на Reserved Instances",
        "Оптимизировать CPU utilization"
      ]
    },
    {
      "name": "CTO",
      "role": "Chief Technology Officer",
      "response": "Технически мы можем упаковать сервисы более эффективно...",
      "recommendations": [
        "Миграция на Kubernetes",
        "Auto-scaling policies"
      ]
    }
  ],
  "summary": "Общая рекомендация: комбинировать техническую оптимизацию с правильной тарификацией...",
  "debug": {
    "parsed_request": {...},
    "compressed_input": {...},
    "response_time_ms": 1234
  }
}
\`\`\`

---

### Endpoint 2: Синглтон агент (один агент)

**Endpoint:** \`POST /api/agent\`

**Назначение:** Вопрос одному конкретному агенту

**Пример curl:**

\`\`\`bash
curl -X POST http://localhost:8000/api/agent \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$ACCESS_TOKEN" \\
  -d '{
    "agent": "ceo",
    "message": "Какую стратегию рекомендуешь на 2025?"
  }'
\`\`\`

**Ожидаемый ответ (200 OK):**

\`\`\`json
{
  "agent": "CEO",
  "response": "На 2025 я рекомендую сфокусироваться на 3 приоритетах...",
  "recommendations": ["Expansion", "AI/ML", "Operational excellence"]
}
\`\`\`

---

### Endpoint 3: Пересчёт summary

**Endpoint:** \`POST /api/summary\`

**Назначение:** Получить итоговую summary на основе истории чата

**Пример curl:**

\`\`\`bash
curl -X POST http://localhost:8000/api/summary \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$ACCESS_TOKEN" \\
  -d '{
    "history": ["...", "..."],
    "mode": "refresh"
  }'
\`\`\`

---

### Endpoint 4: Терапевт (Слой 1)

**Endpoint:** \`POST /api/therapy\`

**Назначение:** Диалог с Терапевтом для артикуляции проблемы

**Пример curl:**

\`\`\`bash
curl -X POST http://localhost:8000/api/therapy \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$ACCESS_TOKEN" \\
  -d '{
    "session_id": null,
    "message": "Менеджеры жалуются, что не понимают, чего я хочу"
  }'
\`\`\`

**Ожидаемый ответ (200 OK):**

\`\`\`json
{
  "session_id": "therapy_sess_abc123",
  "therapist_response": "Интересно! Расскажи подробнее — это касается всех менеджеров или конкретного отдела?",
  "key_insights": [
    {
      "question": "Сколько менеджеров в команде?",
      "answer": "~20 человек",
      "insight_summary": "Команда из 20 менеджеров"
    }
  ],
  "hypotheses": [
    {
      "hypothesis_text": "Проблема в неясной коммуникации целей",
      "confidence": 65
    }
  ],
  "ready_for_board": false
}
\`\`\`

---

## 🧪 Интеграционные тесты

### Тест 1: Full Flow (Логин → Chat → Refresh)

**Цель:** Проверить полный цикл: получение токенов → API запрос → рефреш токена

**Скрипт:**

\`\`\`bash
#!/bin/bash

set -e  # Выходим при первой ошибке

echo "🧪 Интеграционный тест: Full Flow"
echo "=================================="

# Шаг 1: Логин
echo "📤 Шаг 1: Логин..."
LOGIN=\$(curl -s -X POST http://localhost:8000/api/login \\
  -H "Content-Type: application/json" \\
  -d '{"user_id": "test_flow_user"}')

ACCESS_TOKEN=\$(echo \$LOGIN | jq -r '.access_token')
REFRESH_TOKEN=\$(echo \$LOGIN | jq -r '.refresh_token')

if [ -z "\$ACCESS_TOKEN" ] || [ "\$ACCESS_TOKEN" = "null" ]; then
    echo "❌ Ошибка: Не получен access_token"
    exit 1
fi

echo "✅ Токены получены"
echo "   Access Token: \${ACCESS_TOKEN:0:30}..."
echo "   Refresh Token: \${REFRESH_TOKEN:0:30}..."

# Шаг 2: API запрос с access_token
echo ""
echo "📤 Шаг 2: Запрос к /api/board с access_token..."
BOARD_RESPONSE=\$(curl -s -X POST http://localhost:8000/api/board \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$ACCESS_TOKEN" \\
  -d '{
    "message": "Test message from integration test",
    "active_agents": ["cfo"],
    "mode": "initial"
  }')

BOARD_STATUS=\$(echo \$BOARD_RESPONSE | jq -r '.agents[0].name' 2>/dev/null)

if [ "\$BOARD_STATUS" = "null" ] || [ -z "\$BOARD_STATUS" ]; then
    echo "❌ Ошибка: Не получен ответ от Board"
    echo "Ответ: \$BOARD_RESPONSE"
    exit 1
fi

echo "✅ Board ответил"
echo "   Agent: \$BOARD_STATUS"

# Шаг 3: Рефреш токена
echo ""
echo "📤 Шаг 3: Рефреш access_token через refresh_token..."
REFRESH=\$(curl -s -X POST http://localhost:8000/api/refresh \\
  -H "Content-Type: application/json" \\
  -d "{\"refresh_token\": \"\$REFRESH_TOKEN\"}")

NEW_ACCESS_TOKEN=\$(echo \$REFRESH | jq -r '.access_token')

if [ -z "\$NEW_ACCESS_TOKEN" ] || [ "\$NEW_ACCESS_TOKEN" = "null" ]; then
    echo "❌ Ошибка: Не получен новый access_token"
    exit 1
fi

echo "✅ Токен обновлен"
echo "   New Access Token: \${NEW_ACCESS_TOKEN:0:30}..."

# Шаг 4: Повторный API запрос с новым токеном
echo ""
echo "📤 Шаг 4: Повторный запрос с новым access_token..."
BOARD_RESPONSE_2=\$(curl -s -X POST http://localhost:8000/api/board \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer \$NEW_ACCESS_TOKEN" \\
  -d '{
    "message": "Second message with refreshed token",
    "active_agents": ["cto"],
    "mode": "initial"
  }')

BOARD_STATUS_2=\$(echo \$BOARD_RESPONSE_2 | jq -r '.agents[0].name' 2>/dev/null)

if [ "\$BOARD_STATUS_2" = "null" ] || [ -z "\$BOARD_STATUS_2" ]; then
    echo "❌ Ошибка: Второй запрос не прошел"
    exit 1
fi

echo "✅ Второй запрос успешен"

echo ""
echo "✅✅✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅✅✅"
\`\`\`

**Как запустить:**

\`\`\`bash
chmod +x integration_test.sh
./integration_test.sh
\`\`\`

---

### Тест 2: Проверка ошибок авторизации

**Цель:** Убедиться, что API правильно обрабатывает ошибки авторизации

\`\`\`bash
#!/bin/bash

echo "🧪 Тест: Ошибки авторизации"
echo "============================"

# Тест 2.1: Запрос БЕЗ токена
echo "📤 Тест 2.1: Запрос БЕЗ Authorization header..."
RESPONSE=\$(curl -s -w "\\n%{http_code}" -X POST http://localhost:8000/api/board \\
  -H "Content-Type: application/json" \\
  -d '{"message": "test"}')

HTTP_CODE=\$(echo "\$RESPONSE" | tail -1)

if [ "\$HTTP_CODE" = "403" ]; then
    echo "✅ Правильно: HTTP 403 Forbidden"
else
    echo "❌ Ошибка: Ожидали 403, получили \$HTTP_CODE"
fi

# Тест 2.2: Запрос с неверным токеном
echo ""
echo "📤 Тест 2.2: Запрос с неверным токеном..."
RESPONSE=\$(curl -s -w "\\n%{http_code}" -X POST http://localhost:8000/api/board \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer invalid_token_12345" \\
  -d '{"message": "test"}')

HTTP_CODE=\$(echo "\$RESPONSE" | tail -1)

if [ "\$HTTP_CODE" = "401" ]; then
    echo "✅ Правильно: HTTP 401 Unauthorized"
else
    echo "❌ Ошибка: Ожидали 401, получили \$HTTP_CODE"
fi

# Тест 2.3: Рефреш с неверным refresh_token
echo ""
echo "📤 Тест 2.3: Рефреш с неверным refresh_token..."
RESPONSE=\$(curl -s -w "\\n%{http_code}" -X POST http://localhost:8000/api/refresh \\
  -H "Content-Type: application/json" \\
  -d '{"refresh_token": "invalid_refresh_token"}')

HTTP_CODE=\$(echo "\$RESPONSE" | tail -1)

if [ "\$HTTP_CODE" = "401" ]; then
    echo "✅ Правильно: HTTP 401 Unauthorized"
else
    echo "❌ Ошибка: Ожидали 401, получили \$HTTP_CODE"
fi

echo ""
echo "✅ Тесты авторизации завершены"
\`\`\`

---

## 🖥️ Тестирование фронтенда

### Запуск фронтенда локально

\`\`\`bash
# Если используется просто статичные файлы (HTML/CSS/JS):
# Запускаем простой HTTP сервер

cd /workspaces/board-of-directors/frontend

# Python 3
python3 -m http.server 8080

# Или с Python 2
python3 -m SimpleHTTPServer 8080
\`\`\`

**Откроем браузер:**

\`\`\`
http://localhost:8080
\`\`\`

### Проверка авторизации на фронте

**Что проверить:**

1. ✅ При загрузке страницы — фронтенд должен попытаться восстановить token из localStorage
2. ✅ Если token есть — показывает чат (без диалога логина)
3. ✅ Если token нет — выполняет логин через /api/login
4. ✅ Чат отправляется с Bearer token в header Authorization
5. ✅ Если 401 — фронтенд автоматически рефрешит token и переотправляет запрос

**В консоли браузера (F12 → Console):**

\`\`\`javascript
// Проверяем, что token сохранён
localStorage.getItem('authToken')

// Проверяем refresh token
localStorage.getItem('refreshToken')

// Проверяем состояние приложения
console.log(appState.getAuthToken())
\`\`\`

**В консоли браузера (F12 → Network tab):**

1. Откройте Network tab
2. Отправьте сообщение в чате
3. Найдите запрос к \`/api/board\`
4. Проверьте, что в Headers есть \`Authorization: Bearer eyJ...\`

---

## 🐛 Troubleshooting

### Проблема 1: "❌ КРИТИЧНАЯ ОШИБКА: JWT_SECRET_KEY не задана"

**Причина:** Переменная окружения JWT_SECRET_KEY не установлена

**Решение:**

\`\`\`bash
# Проверяем .env
cat .env

# Должна быть строка:
# JWT_SECRET_KEY=...

# Если нет — добавляем:
echo 'JWT_SECRET_KEY=your_secret_key_here_min_32_chars' >> .env

# Перезагружаем приложение (Ctrl+C и python3 main.py)
\`\`\`

---

### Проблема 2: "❌ КРИТИЧНАЯ ОШИБКА: GIGACHAT_AUTH_KEY не задана"

**Причина:** Переменная окружения GIGACHAT_AUTH_KEY не установлена

**Решение:**

\`\`\`bash
# Добавляем в .env
echo 'GIGACHAT_AUTH_KEY=your_gigachat_key_here' >> .env

# Перезагружаем приложение
\`\`\`

---

### Проблема 3: "Не удалось подключиться к серверу" или "Connection refused"

**Причина:** Бэкенд не запущен или запущен на другом порту

**Решение:**

\`\`\`bash
# Проверяем, что бэкенд работает
curl http://localhost:8000/health

# Если не работает:
# 1. Проверяем логи
tail -50 logs/gigachat.log

# 2. Запускаем вручную (если нет процесса)
python3 main.py

# 3. Проверяем, что порт не занят
lsof -i :8000

# 4. Если занят — убиваем процесс
pkill -f "uvicorn main:app"
\`\`\`

---

### Проблема 4: "401 Unauthorized" при каждом запросе

**Причина:** Token истёк или невалиден

**Решение:**

\`\`\`bash
# Проверяем время жизни token (должно быть в секундах):
echo "Access token жизнь: 900 сек (15 минут)"
echo "Refresh token жизнь: 2592000 сек (30 дней)"

# Если часто видите 401 — может быть проблема с часами сервера
# Проверяем время на сервере:
date

# Если время неверно — синхронизируем:
timedatectl set-ntp true
\`\`\`

---

### Проблема 5: "Не удалось обновить access_token" (при refresh)

**Причина:** Refresh token истёк (> 30 дней) или повреждён

**Решение:**

\`\`\`bash
# Требуется новая авторизация (новый логин)
curl -X POST http://localhost:8000/api/login \\
  -H "Content-Type: application/json" \\
  -d '{"user_id": "your_user_id"}'
\`\`\`

---

### Проблема 6: "429 Too Many Requests"

**Причина:** Превышен лимит на запросы (10/minute для /api/board)

**Решение:**

\`\`\`bash
# Подождите 1 минуту и повторите запрос
# Или увеличьте лимит в app/core/config.py:
# RATE_LIMIT_BOARD_CHAT = "20/minute"  # вместо 10/minute
\`\`\`

---

### Проблема 7: "Неверный или истёкший токен" при valid token

**Причина:** JWT_SECRET_KEY не совпадает между сеансами

**Решение:**

\`\`\`bash
# Убедитесь, что JWT_SECRET_KEY одинаков везде:
# 1. В .env файле
# 2. Приложение читает его при старте

# Проверяем .env:
grep JWT_SECRET_KEY .env

# Если меняли .env — перезагружаем приложение:
pkill -f "uvicorn main:app"
python3 main.py
\`\`\`

---

## 📊 Постман коллекция (для удобства)

**Если используете Postman, импортируйте эту коллекцию:**

\`\`\`json
{
  "info": {
    "name": "Board.AI API",
    "description": "Full API testing collection"
  },
  "item": [
    {
      "name": "1. Login",
      "request": {
        "method": "POST",
        "url": "http://localhost:8000/api/login",
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "body": {
          "mode": "raw",
          "raw": "{\"user_id\": \"test_user_{{timestamp}}\"}"
        }
      }
    },
    {
      "name": "2. Board Chat",
      "request": {
        "method": "POST",
        "url": "http://localhost:8000/api/board",
        "header": [
          {"key": "Content-Type", "value": "application/json"},
          {"key": "Authorization", "value": "Bearer {{access_token}}"}
        ],
        "body": {
          "mode": "raw",
          "raw": "{\"message\": \"Test message\", \"active_agents\": [\"cfo\"], \"mode\": \"initial\"}"
        }
      }
    },
    {
      "name": "3. Refresh Token",
      "request": {
        "method": "POST",
        "url": "http://localhost:8000/api/refresh",
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "body": {
          "mode": "raw",
          "raw": "{\"refresh_token\": \"{{refresh_token}}\"}"
        }
      }
    }
  ]
}
\`\`\`

---

## ✅ Чеклист для тестировщика

Перед тем как считать тестирование завершённым:

- [ ] ✅ Переменные окружения установлены в .env
- [ ] ✅ Бэкенд запускается без ошибок (\`python3 main.py\`)
- [ ] ✅ Health check endpoint отвечает
- [ ] ✅ Логин возвращает access + refresh токены
- [ ] ✅ API запросы работают с valid token
- [ ] ✅ 403 ошибка при отсутствии Authorization header
- [ ] ✅ 401 ошибка при неверном token
- [ ] ✅ Refresh token выдаёт новый access token
- [ ] ✅ Refresh token с неверным значением возвращает 401
- [ ] ✅ /api/board возвращает агентов и их ответы
- [ ] ✅ /api/agent работает для одного агента
- [ ] ✅ /api/therapy работает и сохраняет сессии
- [ ] ✅ Rate limiting работает (429 после лимита)
- [ ] ✅ Фронтенд загружается без ошибок
- [ ] ✅ Фронтенд логинится автоматически
- [ ] ✅ Чат отправляет запросы с Bearer token
- [ ] ✅ При 401 фронтенд автоматически рефрешит token
- [ ] ✅ Логи показывают корректную информацию (без сенситивных данных)

---

## 📞 Контакты и поддержка

**Если возникли проблемы:**

1. Проверь, что .env содержит все необходимые переменные
2. Проверь логи: \`tail -100 logs/gigachat.log\`
3. Проверь консоль браузера (F12 → Console)
4. Проверь Network tab в браузере (F12 → Network)
5. Перезагрузи приложение и попробуй ещё раз

**Версия документации:** 1.0 (актуализирована 09.01.2026)  
**Последние изменения:** Переведено на .env (легаси run_backend.sh и .env.example удалены)  
**Готовность к тестированию:** ✅ ГОТОВО
