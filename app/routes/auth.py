"""
Эндпойнты аутентификации.
Логин и обновление JWT токенов.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import create_token_pair, verify_refresh_token, ACCESS_TOKEN_EXPIRE_MINUTES
from db import get_db, create_user_if_not_exists
from app.schemas import LoginRequest, TokenResponse, RefreshTokenRequest, AccessTokenResponse
from app.core.logger import logger

# Создаём router для группировки auth endpoints
router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """
    Логин: принимает user_id, создаёт пользователя, возвращает пару токенов.
    
    Args:
        body: LoginRequest с user_id
        db: сессия БД
        
    Returns:
        TokenResponse: access_token + refresh_token
    """
    create_user_if_not_exists(db, body.user_id)
    token_pair = create_token_pair(body.user_id)
    
    logger.info(f"User {body.user_id} logged in, issued token pair")
    
    return token_pair


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh_access_token(body: RefreshTokenRequest) -> AccessTokenResponse:
    """
    Обновление access_token используя refresh_token.
    Вызывается клиентом когда access_token истекает.
    
    Args:
        body: RefreshTokenRequest с refresh_token
        
    Returns:
        AccessTokenResponse: новый access_token
        
    Raises:
        HTTPException: если refresh_token неверный или истёкший
    """
    # Проверяем refresh_token (выбросит HTTPException если невалиден)
    user_id = verify_refresh_token(body.refresh_token)
    
    # Выдаём новый access_token (из auth.py)
    from auth import create_access_token
    new_access_token = create_access_token(user_id)
    
    logger.info(f"User {user_id} refreshed access token")
    
    return AccessTokenResponse(
        access_token=new_access_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60  # в секундах
    )
