"""Podsystem fallbackowego promptu systemowego kernela agenta Regis."""

from server.agent.prompts.models import AgentDefaultPromptConfig
from server.agent.prompts.store import AgentDefaultPromptStore

__all__ = [
    "AgentDefaultPromptStore",
    "AgentDefaultPromptConfig",
]
