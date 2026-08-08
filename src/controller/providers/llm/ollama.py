import logging
import json
import time
import requests
from requests.exceptions import RequestException
from typing import Generator

from controller.providers.llm.base import LLMBackend
from controller.exceptions import LLMConnectionError
from controller.config import loader as config


class OllamaBackend(LLMBackend):
    def __init__(self, host: str = "http://127.0.0.1:11434", model_name: str = "qwen3.5:9b", temperature: float = 0.5):
        self.host = host.rstrip("/")
        self.model_name = model_name
        self.temperature = temperature
        logging.info(f"Zainicjalizowano OllamaBackend: Model={model_name}, Temp={temperature}")

    def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None
    ) -> Generator[dict, None, None]:
        """
        Wysyła jednorazowe zapytanie strumieniowe do API Ollama (`/api/chat`) i generuje zdarzenia:
        - {"type": "content", "content": piece}
        - {"type": "profiler", "metric": "llm_ttft", "value": ms}
        - {"type": "tool_calls", "tool_calls": [...]}
        """
        settings = config.load_config("settings")
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/chat"

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": self.temperature
            }
        }

        if tools:
            payload["tools"] = tools

        try:
            t_req_start = time.time()
            t_first_token = None

            response = requests.post(url, json=payload, timeout=120, stream=True)
            if response.status_code != 200:
                raise LLMConnectionError(f"HTTP {response.status_code}: {response.text}")

            final_tool_calls = []

            for line in response.iter_lines():
                if not line:
                    continue

                decoded_line = line.decode("utf-8")
                try:
                    chunk = json.loads(decoded_line)
                    msg = chunk.get("message", {})

                    if "content" in msg and msg["content"]:
                        piece = msg["content"]
                        if t_first_token is None:
                            t_first_token = time.time()
                            ttft_ms = (t_first_token - t_req_start) * 1000.0
                            yield {"type": "profiler", "metric": "llm_ttft", "value": ttft_ms}

                        yield {"type": "content", "content": piece}

                    if "tool_calls" in msg and msg["tool_calls"]:
                        final_tool_calls = msg["tool_calls"]

                except json.JSONDecodeError:
                    continue

            if t_first_token is not None:
                gen_ms = (time.time() - t_first_token) * 1000.0
                yield {"type": "profiler", "metric": "llm_gen", "value": gen_ms}

            if final_tool_calls:
                yield {"type": "tool_calls", "tool_calls": final_tool_calls}

        except RequestException as e:
            logging.error(f"Ollama API Error: {e}")
            raise LLMConnectionError(f"Błąd komunikacji z modelem: {e}")

    def is_available(self) -> bool:
        settings = config.load_config("settings")
        tags_url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/tags"
        try:
            response = requests.get(tags_url, timeout=2)
            return response.status_code == 200
        except RequestException:
            return False

    def get_provider_name(self) -> str:
        return "ollama"

    def preload_model(self) -> None:
        settings = config.load_config("settings")
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
        settings = config.load_config("settings")
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/generate"
        payload = {"model": self.model_name, "keep_alive": 0}
        try:
            requests.post(url, json=payload, timeout=5)
            logging.info(f"Wysłano żądanie wyładowania modelu {self.model_name} z VRAM.")
        except Exception as e:
            logging.warning(f"Nie udało się wyładować modelu: {e}")
