#!/bin/bash

echo "🧪🧪🧪 ЗАПУСК ВСЕХ ТЕСТОВ 🧪🧪🧪"
echo "========================================"
echo ""

API_URL="http://localhost:8000"

# Проверка, что бэкенд работает
echo "🔍 Проверка здоровья приложения..."
HEALTH=$(curl -s "$API_URL/health")
HEALTH_STATUS=$(echo $HEALTH | jq -r '.status' 2>/dev/null)

if [ "$HEALTH_STATUS" = "ok" ]; then
    echo "✅ Бэкенд работает"
else
    echo "❌ ОШИБКА: Бэкенд не отвечает на $API_URL"
    echo "   Убедитесь, что приложение запущено: python main.py"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════"
echo "Запуск тестов..."
echo "════════════════════════════════════════════"
echo ""

# Запуск интеграционных тестов
echo "1️⃣ INTEGRATION TESTS (Full Flow)"
echo "────────────────────────────────"
bash $(dirname "$0")/integration_test.sh
INT_RESULT=$?

echo ""
echo "2️⃣ AUTHORIZATION ERROR TESTS"
echo "────────────────────────────"
bash $(dirname "$0")/auth_error_test.sh
AUTH_RESULT=$?

echo ""
echo "════════════════════════════════════════════"

if [ $INT_RESULT -eq 0 ] && [ $AUTH_RESULT -eq 0 ]; then
    echo "✅✅✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ ✅✅✅"
    echo "════════════════════════════════════════════"
    exit 0
else
    echo "❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ"
    echo "════════════════════════════════════════════"
    exit 1
fi
