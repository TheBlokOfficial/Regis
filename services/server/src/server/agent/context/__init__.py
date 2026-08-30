"""Podsystem budowania kontekstu i zarządzania promptami systemowymi dla agenta Regis."""

from server.agent.context.builder import DEFAULT_SYSTEM_PROMPT, ContextBuilder

__all__ = [
    "ContextBuilder",
    "DEFAULT_SYSTEM_PROMPT",
]
