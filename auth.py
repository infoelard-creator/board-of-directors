import os
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel

load_dotenv()

# ✅ FIX B4: ОБЯЗАТЕЛЬНАЯ ПЕРЕМЕННАЯ ОКРУЖЕНИЯ ДЛЯ JWT СЕКРЕТА
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
ACCESS_TOKEN_EXPIRE_MINUTES = 15  # Короткоживущий: 15 минут
REFRESH_TOKEN_EXPIRE_DAYS = 30     # Долгоживущий: 30 дней

security = HTTPBearer()


# ============================================
# Pydantic Models
# ============================================

class TokenResponse(BaseModel):
    """Ответ при логине — оба токена."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # в секундах


class AccessTokenResponse(BaseModel):
    """Ответ при обновлении access_token'а."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # в секундах


class RefreshTokenRequest(BaseModel):
    """Request для /api/refresh endpoint'а."""
    refresh_token: str


# ============================================
# Token Creation Functions
# ============================================

def create_access_token(user_id: str) -> str:
    """
    Создаёт ACCESS TOKEN на 15 минут.
    Используется для API запросов.
    """
    now = datetime.now(timezone.utc)
    expire_time = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire_timestamp = int(expire_time.timestamp())

    if expire_timestamp % 60 != 0:
        expire_timestamp = (expire_timestamp // 60 + 1) * 60

    expire = datetime.fromtimestamp(expire_timestamp, tz=timezone.utc)

    to_encode = {
        "user_id": user_id,
        "token_type": "access",
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(user_id: str) -> str:
    """
    Создаёт REFRESH TOKEN на 30 дней.
    Используется только для получения нового access_token'а.
    """
    now = datetime.now(timezone.utc)
    expire_time = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    expire_timestamp = int(expire_time.timestamp())

    if expire_timestamp % 60 != 0:
        expire_timestamp = (expire_timestamp // 60 + 1) * 60

    expire = datetime.fromtimestamp(expire_timestamp, tz=timezone.utc)

    to_encode = {
        "user_id": user_id,
        "token_type": "refresh",
        "exp": expire
    }
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_token_pair(user_id: str) -> TokenResponse:
    """
    Выдает пару токенов: access + refresh.
    Вызывается при логине.
    """
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60  # в секундах
    )


# ============================================
# Token Verification Functions
# ============================================

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Проверяет ACCESS TOKEN и возвращает user_id.

    Args:
        credentials: HTTP Authorization credentials

    Returns:
        user_id из токена

    Raises:
        HTTPException: если токен неверный, истёкший или не access_token
    """
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        token_type: str = payload.get("token_type", "access")
        
        # Убедимся что это access token
        if token_type != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Требуется access_token, а не refresh_token",
            )
        
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


def verify_refresh_token(refresh_token: str) -> str:
    """
    Проверяет REFRESH TOKEN и возвращает user_id.
    Вызывается в /api/refresh endpoint'е.

    Args:
        refresh_token: токен обновления

    Returns:
        user_id из токена

    Raises:
        HTTPException: если токен неверный, истёкший или не refresh_token
    """
    try:
        payload = jwt.decode(refresh_token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("user_id")
        token_type: str = payload.get("token_type", "refresh")
        
        # Убедимся что это refresh token
        if token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный тип токена",
            )
        
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный refresh_token",
            )
        return user_id
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный или истёкший refresh_token",
        )
