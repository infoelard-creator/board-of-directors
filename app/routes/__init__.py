"""
API маршруты приложения.
Содержит все endpoints, разделённые по функциональности.
"""

from app.routes.auth import router as auth_router
from app.routes.agent import router as agent_router
from app.routes.board import router as board_router
from app.routes.therapy import router as therapy_router

__all__ = [
    "auth_router",
    "agent_router",
    "board_router",
    "therapy_router",
]
