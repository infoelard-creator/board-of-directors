#!/bin/bash

set -e

echo "🧪 Интеграционный тест: Full Flow"
echo "=================================="
echo ""

# Конфигурация
API_URL="http://localhost:8000"
USER_ID="test_flow_user_$(date +%s)"

echo "📋 Конфигурация:"
echo "   API URL: $API_URL"
echo "   User ID: $USER_ID"
echo ""

# ===== Шаг 1: Логин =====
echo "📤 Шаг 1: POST /api/login (получить access + refresh токены)"
LOGIN=$(curl -s -X POST "$API_URL/api/login" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$USER_ID\"}")

ACCESS_TOKEN=$(echo $LOGIN | jq -r '.access_token')
REFRESH_TOKEN=$(echo $LOGIN | jq -r '.refresh_token')

if [ -z "$ACCESS_TOKEN" ] || [ "$ACCESS_TOKEN" = "null" ]; then
    echo "❌ ОШИБКА: Не получен access_token"
    echo "Ответ сервера: $LOGIN"
    exit 1
fi

echo "✅ Токены получены"
echo "   Access Token: ${ACCESS_TOKEN:0:30}..."
echo "   Refresh Token: ${REFRESH_TOKEN:0:30}..."
echo ""

# ===== Шаг 2: Запрос к Board с access_token =====
echo "📤 Шаг 2: POST /api/board (чат с агентами)"
BOARD_RESPONSE=$(curl -s -X POST "$API_URL/api/board" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -d '{
    "message": "Test message from integration test",
    "active_agents": ["cfo"],
    "mode": "initial"
  }')

BOARD_STATUS=$(echo $BOARD_RESPONSE | jq -r '.agents[0].agent' 2>/dev/null)

if [ "$BOARD_STATUS" = "null" ] || [ -z "$BOARD_STATUS" ]; then
    echo "❌ ОШИБКА: Не получен ответ от Board"
    echo "Ответ сервера: $BOARD_RESPONSE"
    exit 1
fi

echo "✅ Board ответил"
echo "   Agent: $BOARD_STATUS"
echo "   Agents count: $(echo $BOARD_RESPONSE | jq '.agents | length')"
echo ""

# ===== Шаг 3: Рефреш токена =====
echo "📤 Шаг 3: POST /api/refresh (обновить access_token)"
REFRESH=$(curl -s -X POST "$API_URL/api/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\": \"$REFRESH_TOKEN\"}")

NEW_ACCESS_TOKEN=$(echo $REFRESH | jq -r '.access_token')

if [ -z "$NEW_ACCESS_TOKEN" ] || [ "$NEW_ACCESS_TOKEN" = "null" ]; then
    echo "❌ ОШИБКА: Не получен новый access_token"
    echo "Ответ сервера: $REFRESH"
    exit 1
fi

echo "✅ Токен обновлен"
echo "   New Access Token: ${NEW_ACCESS_TOKEN:0:30}..."
echo ""

# ===== Шаг 4: Повторный запрос с новым токеном =====
echo "📤 Шаг 4: POST /api/board (запрос с новым access_token)"
BOARD_RESPONSE_2=$(curl -s -X POST "$API_URL/api/board" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $NEW_ACCESS_TOKEN" \
  -d '{
    "message": "Second message with refreshed token",
    "active_agents": ["cto"],
    "mode": "initial"
  }')

BOARD_STATUS_2=$(echo $BOARD_RESPONSE_2 | jq -r '.agents[0].agent' 2>/dev/null)

if [ "$BOARD_STATUS_2" = "null" ] || [ -z "$BOARD_STATUS_2" ]; then
    echo "❌ ОШИБКА: Второй запрос не прошел"
    echo "Ответ сервера: $BOARD_RESPONSE_2"
    exit 1
fi

echo "✅ Второй запрос успешен"
echo "   Agent: $BOARD_STATUS_2"
echo ""

echo "════════════════════════════════════════════"
echo "✅✅✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅✅✅"
echo "════════════════════════════════════════════"
