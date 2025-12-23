import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

# ✅ FIX B4: ОБЯЗАТЕЛЬНАЯ ПЕРЕМЕННАЯ ОКРУЖЕНИЯ ДЛЯ JWT СЕКРЕТА
# Если не задана → приложение падает при старте с понятной ошибкой
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY:
    raise RuntimeError("""
❌ КРИТИЧНАЯ ОШИБКА: Переменная окружения JWT_SECRET_KEY не задана!
Это критично для безопасности приложения.

Установите её перед запуском:
  export JWT_SECRET_KEY='your-secret-key-here-min-32-chars'

Или в .env файле:
  JWT_SECRET_KEY=your-secret-key-here-min-32-chars

Сгенерировать безопасный ключ:
  openssl rand -base64 32
""")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 7 * 24 * 60  # 7 дней

security = HTTPBearer()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


def create_access_token(user_id: str) -> str:
    """
    Создаёт JWT токен доступа для пользователя.

    Args:
        user_id: ID пользователя

    Returns:
        Подписанный JWT токен
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"user_id": user_id, "exp": expire}
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Проверяет JWT токен и возвращает user_id.

    Args:
        credentials: HTTP Authorization credentials

    Returns:
        user_id из токена

    Raises:
        HTTPException: если токен неверный или истёкший
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен",
            )
        return user_id
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или истёкший токен",
        )
