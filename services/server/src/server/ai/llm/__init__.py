"""Konkretne backendy i logika selekcji dostawców modeli LLM.

Protokół (`BaseLLMProvider` i wspólne dataclassy) mieszka w `server.ports.llm` —
to kernel jest jego właścicielem, dokładnie jak `WorldInterface`
(`agent/context_provider.py`). Ten pakiet trzyma wyłącznie konkrety
(`OllamaProvider`, `OpenAICompatibleProvider` — wspólna implementacja dla
OpenRouter i Groq, rozróżnianych na poziomie `ProviderType`/`LLMFactory`, nie
osobnymi klasami) i logikę wyboru/persystencji (`LLMFactory`, `BackendRegistry`).
"""

from server.ai.llm.factory import LLMFactory
from server.ai.llm.models import BackendFileContent, BackendInstanceConfig, ProviderType
from server.ai.llm.providers import OllamaProvider, OpenAICompatibleProvider
from server.ai.llm.registry import BackendRegistry
from server.ai.llm.router import LLMRouter

__all__ = [
    "BackendFileContent",
    "BackendInstanceConfig",
    "BackendRegistry",
    "LLMFactory",
    "LLMRouter",
    "OllamaProvider",
    "OpenAICompatibleProvider",
    "ProviderType",
]
