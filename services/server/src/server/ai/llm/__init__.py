"""Konkretne backendy i logika selekcji dostawców modeli LLM.

Protokół (`BaseLLMProvider` i wspólne dataclassy) zostaje w `server.agent.llm` —
to kernel jest jego właścicielem, dokładnie jak `WorldInterface`
(`agent/context_provider.py`). Ten pakiet trzyma wyłącznie konkrety
(`OllamaProvider`, `OpenRouterProvider`, `GroqProvider`) i logikę wyboru/
persystencji (`LLMFactory`, `BackendRegistry`).
"""

from server.ai.llm.factory import LLMFactory
from server.ai.llm.models import ActiveBackendConfig, BackendFileContent, BackendInstanceConfig, ProviderType
from server.ai.llm.providers import GroqProvider, OllamaProvider, OpenRouterProvider
from server.ai.llm.registry import BackendRegistry
from server.ai.llm.router import LLMRouter

__all__ = [
    "ActiveBackendConfig",
    "BackendFileContent",
    "BackendInstanceConfig",
    "BackendRegistry",
    "GroqProvider",
    "LLMFactory",
    "LLMRouter",
    "OllamaProvider",
    "OpenRouterProvider",
    "ProviderType",
]
