import logging
import requests
from requests.exceptions import RequestException
from typing import Any

from core.llm_backends.base import LLMBackend
from core.exceptions import LLMConnectionError
from core.stream_parser import StreamingTokenParser
from core import config
from core.agents.react_agent import ReActAgent

class OllamaBackend(LLMBackend):
    def __init__(self, model_name: str, temperature: float = 0.1):
        self.model_name = model_name
        self.temperature = temperature
        logging.info(f"Zainicjalizowano OllamaBackend: Model={model_name}, Temp={temperature}")

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
        parser = StreamingTokenParser(on_thought_token, on_content_token)
        agent = ReActAgent(self.model_name, self.temperature)
        return agent.generate_response(messages, tools_registry, parser, on_tool_call, on_thought_token, on_content_token, on_raw_tool_call, on_profiler=on_profiler)

    def is_available(self) -> bool:
        settings = config.load_settings()
        tags_url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/tags"
        try:
            response = requests.get(tags_url, timeout=2)
            return response.status_code == 200
        except RequestException:
            return False

    def get_provider_name(self) -> str:
        return "ollama"

    def preload_model(self) -> None:
        settings = config.load_settings()
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/generate"
        payload = {"model": self.model_name, "keep_alive": -1}
        try:
            response = requests.post(url, json=payload, timeout=(3, 120))
            response.raise_for_status()
            logging.info(f"Wstępnie załadowano model {self.model_name} do VRAM.")
        except RequestException as e:
            logging.error(f"Nie udało się połączyć z Ollamą lub załadować modelu: {e}")
            raise LLMConnectionError(f"Ollama Preload Error: {e}")

    def unload_model(self) -> None:
        settings = config.load_settings()
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/generate"
        payload = {"model": self.model_name, "keep_alive": 0}
        try:
            requests.post(url, json=payload, timeout=5)
            logging.info(f"Wysłano żądanie wyładowania modelu {self.model_name} z VRAM.")
        except Exception as e:
            logging.warning(f"Nie udało się wyładować modelu: {e}")
