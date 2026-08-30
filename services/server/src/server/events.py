"""Moduł definicji i kontraktów zdarzeń wewnętrznych serwera Regis."""

from enum import Enum


class ServerEventType(str, Enum):
    """Typy ogólno-serwerowych zdarzeń w magistrali EventBus."""

    CHAT_USER_MESSAGE = "chat.user_message"
    CHAT_CHUNK = "chat.chunk"
    CHAT_DONE = "chat.done"
    CHAT_ERROR = "chat.error"
    CHAT_CANCELLED = "chat.cancelled"
    TOOL_CALL_START = "chat.tool_call_start"
    TOOL_CALL_RESULT = "chat.tool_call_result"
