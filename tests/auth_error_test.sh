#!/bin/bash

echo "🧪 Тест: Ошибки авторизации"
echo "============================"
echo ""

API_URL="http://localhost:8000"

# ===== Тест 1: Запрос БЕЗ Authorization header =====
echo "📤 Тест 1: POST /api/board БЕЗ Authorization header"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/board" \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "403" ]; then
    echo "✅ Правильно: HTTP 403 Forbidden"
else
    echo "❌ Ошибка: Ожидали 403, получили $HTTP_CODE"
    echo "   Body: $BODY"
fi
echo ""

# ===== Тест 2: Запрос с неверным токеном =====
echo "📤 Тест 2: POST /api/board с неверным Bearer token"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/board" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer invalid_token_12345" \
  -d '{"message": "test"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "401" ]; then
    echo "✅ Правильно: HTTP 401 Unauthorized"
else
    echo "❌ Ошибка: Ожидали 401, получили $HTTP_CODE"
    echo "   Body: $BODY"
fi
echo ""

# ===== Тест 3: Рефреш с неверным refresh_token =====
echo "📤 Тест 3: POST /api/refresh с неверным refresh_token"
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/api/refresh" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token": "invalid_refresh_token_xyz"}')

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

if [ "$HTTP_CODE" = "401" ]; then
    echo "✅ Правильно: HTTP 401 Unauthorized"
else
    echo "❌ Ошибка: Ожидали 401, получили $HTTP_CODE"
    echo "   Body: $BODY"
fi
echo ""

echo "════════════════════════════════════════════"
echo "✅ Тесты авторизации завершены"
echo "════════════════════════════════════════════"
