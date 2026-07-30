import logging
import requests
from requests.exceptions import RequestException
from typing import Any

from core.exceptions import LLMConnectionError
from core.stream_parser import StreamingTokenParser
from core import config

from core.agents.nlu_agent import NLUAgent
from core.agents.react_agent import ReActAgent


class LLMEngine:
    """Silnik odpowiadający za komunikację z lokalnym serwerem Ollama (Fasada).
    Rozdziela zadania na specjalistycznych agentów: NLUAgent (dla Butlera) i ReActAgent (dla Regisa).
    """

    def __init__(self, model_name: str, tier: str, temperature: float = 0.1, history_limit: int = 20):
        self.model_name = model_name
        self.tier = tier
        self.temperature = temperature
        # history_limit zostaje w sygnaturze dla kompatybilności wstecznej, 
        # ale stan historii przeniósł się do Kontrolera.
        logging.info(f"Zainicjalizowano LLMEngine: Model={model_name}, Tier={self.tier}, Temp={temperature}")

    @staticmethod
    def get_available_models() -> list[str]:
        settings = config.load_settings()
        tags_url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/tags"
        try:
            response = requests.get(tags_url, timeout=5)
            response.raise_for_status()
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
        except RequestException as e:
            logging.error(f"Nie można połączyć się z serwerem Ollama: {e}")
            raise LLMConnectionError(f"Ollama API Error: {e}")

    def clear_history(self) -> None:
        logging.info("Wyczyszczono historię konwersacji LLM (No-op, historia jest w Kontrolerze).")

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

    def generate_response(self, messages: list[dict], tools_registry, on_tool_call: Any = None, on_thought_token: Any = None, on_content_token: Any = None, on_raw_tool_call: Any = None, on_profiler: Any = None) -> str:
        """Puszcza gotową paczkę messages (od Kontrolera) do odpowiedniego Agenta."""
        parser = StreamingTokenParser(on_thought_token, on_content_token)

        # Wzorzec Strategii - Delegacja
        if self.tier == "butler":
            agent = NLUAgent(self.model_name)
            return agent.generate_response(messages, tools_registry, on_tool_call, on_thought_token, on_content_token, on_raw_tool_call)
        else:
            agent = ReActAgent(self.model_name, self.temperature)
            return agent.generate_response(messages, tools_registry, parser, on_tool_call, on_thought_token, on_content_token, on_raw_tool_call, on_profiler=on_profiler)
