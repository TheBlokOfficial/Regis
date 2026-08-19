"""Podsystem fallbackowego promptu systemowego kernela Agenta Regis OS."""

from server.agent.prompts.store import AgentDefaultPromptStore
from server.agent.prompts.models import AgentDefaultPromptConfig

__all__ = [
    "AgentDefaultPromptStore",
    "AgentDefaultPromptConfig",
]
