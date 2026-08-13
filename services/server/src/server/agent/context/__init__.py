"""Podsystem budowania kontekstu i zarządzania promptami systemowymi dla Agenta Regis OS."""

from server.agent.context.builder import ContextBuilder, DEFAULT_SYSTEM_PROMPT

__all__ = [
    "ContextBuilder",
    "DEFAULT_SYSTEM_PROMPT",
]
