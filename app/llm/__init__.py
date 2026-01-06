"""
LLM слой приложения.
Содержит всю логику работы с GigaChat API и обработки данных.
"""

from app.llm.client import (
    get_gigachat_token,
    ask_gigachat,
    expand_agent_output,
    create_debug_metadata,
)

from app.llm.processor import (
    parse_user_request,
    compress_user_message,
    compress_history,
)

__all__ = [
    # client.py
    "get_gigachat_token",
    "ask_gigachat",
    "expand_agent_output",
    "create_debug_metadata",
    # processor.py
    "parse_user_request",
    "compress_user_message",
    "compress_history",
]
