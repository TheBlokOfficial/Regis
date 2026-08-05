import json
import time
import logging
import httpx
from typing import Any, AsyncGenerator

from client.utils import LLMConnectionError
from client import config


class LLMEngine:
    """Silnik wnioskowania LLM oparty na Ollama API.
    Bezstanowy, asynchroniczny klient streamingowy (Ultra-Dumb Worker).
    Nie wykonuje narzędzi ani nie utrzymuje historii – przyjmuje gotową listę wiadomości.
    """

    def __init__(self, model_name: str, temperature: float = 0.1):
        self.model_name = model_name
        self.temperature = temperature
        settings = config.load_settings()
        self.ollama_url = settings.get('ollama_url', 'http://127.0.0.1:11434')
        logging.info(f"Zainicjalizowano LLMEngine (Ollama): model={model_name}, temp={temperature}, url={self.ollama_url}")

    def _parse_chunk(self, line: str) -> dict | None:
        """Parsuje pojedynczą linię JSON z surowego strumienia Ollamy."""
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    async def _process_stream(
        self, 
        response: httpx.Response, 
        t_req_start: float
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Przetwarza strumień HTTP (yield-uje eventy sieciowe)."""
        t_first_token = None
        full_content = ""
        final_tool_calls = []

        async for line in response.aiter_lines():
            chunk = self._parse_chunk(line)
            if not chunk:
                continue

            msg = chunk.get("message", {})
            content = msg.get("content")

            # Obsługa pojawienia się pierwszego tokenu tekstu (Time To First Token)
            if content and t_first_token is None:
                t_first_token = time.time()
                yield {"type": "profiler", "content": {"metric": "llm_ttft", "value": (t_first_token - t_req_start) * 1000.0}}

            if content:
                full_content += content
                yield {"type": "content", "content": content}

            if msg.get("tool_calls"):
                final_tool_calls = msg["tool_calls"]

        # Zakończenie strumienia - metryka czasu generowania reszty tekstu
        if t_first_token is not None:
            gen_ms = (time.time() - t_first_token) * 1000.0
            yield {"type": "profiler", "content": {"metric": "llm_gen", "value": gen_ms}}

        # Emitowanie zebranych danych na koniec (done + tool_calls)
        yield {
            "type": "done", 
            "content": full_content,
            "tool_calls": final_tool_calls if final_tool_calls else None
        }

    async def generate_response_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Generuje odpowiedź ze strumieniem tokenów. Przekazuje tool_calls w zdarzeniu 'done' bez ich wykonywania."""
        url = f"{self.ollama_url}/api/chat"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "options": {"temperature": self.temperature}
        }
        if tools:
            payload["tools"] = tools

        t_req_start = time.time()

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        raise LLMConnectionError(f"HTTP {response.status_code}: {err_text.decode('utf-8')}")

                    async for event in self._process_stream(response, t_req_start):
                        yield event

        except httpx.RequestError as e:
            logging.error(f"Ollama API Error: {e}")
            raise LLMConnectionError(f"Błąd komunikacji z modelem: {e}")
