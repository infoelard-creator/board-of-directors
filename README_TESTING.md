# 🧪 QUICK START: Тестирование Board.AI

**Дата:** 09.01.2026 | **Версия:** 1.0.0

## ⚡ Быстрый старт

### Шаг 1: Запуск бэкенда (Терминал 1)

```bash
cd /workspaces/board-of-directors
source venv/bin/activate
python3 main.py
```

**Ожидаемый вывод:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete
```

### Шаг 2: Запуск тестов (Терминал 2)

```bash
cd /workspaces/board-of-directors
bash tests/run_all_tests.sh
```

## 📊 Что проверяется?

✅ **Integration Test** (Full Flow)
  - POST /api/login → получение access + refresh токенов
  - POST /api/board → запрос с Bearer token
  - POST /api/refresh → обновление access_token
  - POST /api/board (повтор) → запрос с новым токеном

✅ **Authorization Error Tests**
  - HTTP 403 при отсутствии Authorization header
  - HTTP 401 при неверном Bearer token
  - HTTP 401 при невалидном refresh_token

## 📁 Структура тестов

```
tests/
├── run_all_tests.sh       # Запустить все тесты
├── integration_test.sh     # Full Flow тест
└── auth_error_test.sh      # Тесты авторизации
```

## 🐛 Troubleshooting

**❌ "Connection refused" или "не удалось подключиться"**
→ Убедись, что бэкенд запущен: `python3 main.py`

**❌ "JWT_SECRET_KEY не задана"**
→ Проверь .env файл содержит все переменные: `cat .env`

**❌ "Не получен access_token"**
→ Посмотри логи: `tail -50 logs/gigachat.log`

## ✅ Статус

**Версия документации:** 1.0
**Готовность к тестированию:** ✅ ГОТОВО

Для полной документации см. `TESTING_GUIDE.md`
