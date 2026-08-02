import logging
from typing import Any

from node.llm_backends.base import LLMBackend
from node.llm_backends.ollama import OllamaBackend

class LLMEngine:
    """Fasada dla wstecznej kompatybilności Węzła Roboczego (WorkerNode).
    Inicjalizuje odpowiedni backend (obecnie Ollama dla workerów).
    """

    def __init__(self, model_name: str, temperature: float = 0.1, history_limit: int = 20):
        # Węzeł roboczy z definicji obsługuje lokalny model
        self.backend = OllamaBackend(model_name=model_name, temperature=temperature)
        logging.info("Zainicjalizowano LLMEngine (Fasada)")

    @staticmethod
    def get_available_models() -> list[str]:
        # Kompatybilność wsteczna, jeśli by coś wywoływało
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

    def preload_model(self) -> None:
        if hasattr(self.backend, "preload_model"):
            self.backend.preload_model()

    def unload_model(self) -> None:
        if hasattr(self.backend, "unload_model"):
            self.backend.unload_model()

    def generate_response(
        self, 
        messages: list[dict], 
        tools_registry: Any, 
        on_tool_call: Any = None, 
        on_thought_token: Any = None, 
        on_content_token: Any = None, 
        on_raw_tool_call: Any = None, 
        on_profiler: Any = None
    ) -> str:
        """Fasada puszczająca zapytanie do właściwego backendu."""
        return self.backend.generate_response(
            messages=messages,
            tools_registry=tools_registry,
            on_tool_call=on_tool_call,
            on_thought_token=on_thought_token,
            on_content_token=on_content_token,
            on_raw_tool_call=on_raw_tool_call,
            on_profiler=on_profiler
        )
