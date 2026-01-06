"""
Board.AI — Clarity Feedback Loop для менеджеров AI-native компаний.

Главное приложение FastAPI.
Собирает все модули в единое целое.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.core.config import CORS_ORIGINS
from app.core.logger import logger
from app.routes import auth_router, agent_router, board_router
from db import init_db

# ===== ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ =====

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="Board.AI",
    description="Clarity Feedback Loop — когнитивный протез для менеджеров",
    version="1.0.0",
)

# ===== MIDDLEWARE =====

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS (кроссоригинные запросы)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["Content-Type", "Authorization"],
)

# ===== ИНИЦИАЛИЗАЦИЯ БД =====

@app.on_event("startup")
def on_startup():
    """Инициализация при запуске приложения."""
    logger.info("Starting up Board.AI application")
    init_db()
    logger.info("Database initialized")


@app.on_event("shutdown")
def on_shutdown():
    """Cleanup при остановке приложения."""
    logger.info("Shutting down Board.AI application")


# ===== РЕГИСТРАЦИЯ ROUTERS =====

app.include_router(auth_router)
app.include_router(agent_router)
app.include_router(board_router)

logger.info("All routers registered | routes: /api/login, /api/refresh, /api/board, /api/agent, /api/summary")


# ===== HEALTH CHECK =====

@app.get("/health")
async def health_check():
    """Простой health check endpoint."""
    return {"status": "ok", "service": "board-ai"}


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting uvicorn server on 0.0.0.0:8000")
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )
