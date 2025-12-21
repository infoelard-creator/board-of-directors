#!/bin/bash
cd /home/user1/board

# активируем venv
. venv/bin/activate

# переменные окружения
export GIGACHAT_AUTH_KEY="NmQzNzhiYjItOGQzOS00NjhlLWJjMzAtNWI0MDBiMjlkNTZiOjhkZjU1YjY2LThkNTEtNDU1Mi04ODkzLTVhYzUyYWE4MTFmMg=="
export JWT_SECRET_KEY="C_e88fSRvnSy4nUd3lPB2L8AwgE02cZz8qLJHkw-u4A"

# гасим старый uvicorn (если есть)
pkill -f "uvicorn main:app" || true

# запускаем новый бэк
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
