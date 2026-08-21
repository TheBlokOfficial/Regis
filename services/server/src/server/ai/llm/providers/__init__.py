"""Konkretne adaptery dostawców modeli LLM dla serwera Regis."""

from server.ai.llm.providers.ollama import OllamaProvider
from server.ai.llm.providers.openai_compatible import OpenAICompatibleProvider

__all__ = [
    "OllamaProvider",
    "OpenAICompatibleProvider",
]
