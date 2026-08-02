import logging
from typing import Any, AsyncGenerator

from node.llm_backends.base import LLMBackend
from node.llm_backends.ollama import OllamaBackend
from node.utils import build_messages_from_history

class LLMEngine:
    """Fasada Węzła Roboczego dla komunikacji asynchronicznej.
    Inicjalizuje odpowiedni backend (Ollama) i obudowuje generowanie.
    """

    def __init__(self, model_name: str, temperature: float = 0.1):
        # Węzeł roboczy z definicji obsługuje lokalny model
        self.backend = OllamaBackend(model_name=model_name, temperature=temperature)
        logging.info("Zainicjalizowano LLMEngine (Fasada)")

    @staticmethod
    def get_available_models() -> list[str]:
        # Kompatybilność wsteczna (używa requests synchronicznie na potrzeby rzadkich zapytań)
        settings = dict()
        try:
            from node import config
            settings = config.load_settings()
        except ImportError:
            pass
        import requests
        tags_url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/tags"
        try:
            response = requests.get(tags_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
        except Exception:
            return []

    def clear_history(self) -> None:
        logging.info("Wyczyszczono historię konwersacji LLM (No-op, historia jest w Kontrolerze).")

    async def preload_model(self) -> None:
        if hasattr(self.backend, "preload_model"):
            await self.backend.preload_model()

    async def unload_model(self) -> None:
        if hasattr(self.backend, "unload_model"):
            await self.backend.unload_model()

    async def generate_response_stream(
        self, 
        system_prompt: str,
        history: list[dict],
        current_message: str,
        tools_registry: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Fasada puszczająca asynchroniczne zapytanie do właściwego backendu.
        Automatycznie buduje strukturę konwersacji z surowej historii.
        """
        
        messages = build_messages_from_history(
            system_prompt=system_prompt,
            history=history,
            current_message=current_message
        )
        
        async for event in self.backend.generate_stream(messages, tools_registry):
            yield event
