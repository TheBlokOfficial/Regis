"""Konkretne adaptery dostawców modeli LLM dla serwera Regis."""

from server.ai.llm.providers.groq import GroqProvider
from server.ai.llm.providers.ollama import OllamaProvider
from server.ai.llm.providers.openrouter import OpenRouterProvider

__all__ = [
    "GroqProvider",
    "OllamaProvider",
    "OpenRouterProvider",
]
