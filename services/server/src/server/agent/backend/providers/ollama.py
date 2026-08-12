import json
from typing import Any, AsyncIterator
import httpx
from shared import get_logger

from server.config import load_settings
from server.agent.backend.providers.base import BaseLLMProvider, LLMMessage

logger = get_logger("regis.agent.providers.ollama")


class OllamaProvider(BaseLLMProvider):
    """Dostawca LLM komunikujący się z lokalnym serwerem Ollama (REST API ze strumieniowaniem)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }

        if "options" in kwargs:
            payload["options"] = kwargs["options"]

        logger.debug(f"Strumieniowanie z Ollamy [{url}] (model: '{payload['model']}')...")

        timeout_val = load_settings().llm_timeout
        httpx_timeout = httpx.Timeout(timeout_val, connect=5.0)

        try:
            async with httpx.AsyncClient(timeout=httpx_timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            message_data = data.get("message", {})
                            content = message_data.get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError as e:
            logger.error(
                f"Nie można połączyć się z serwerem Ollama pod adresem {self.base_url}. "
                f"Upewnij się, że usługa Ollama jest uruchomiona."
            )
            raise RuntimeError(f"Błąd połączenia z Ollamą: {e}") from e
        except httpx.ReadTimeout as e:
            logger.error(f"Przekroczono limit czasu oczekiwania na tokeny ({timeout_val}s) z Ollamy.")
            raise RuntimeError(f"Timeout strumienia z Ollama ({timeout_val}s): {e}") from e
        except Exception as e:
            logger.error(f"Błąd podczas strumieniowania odpowiedzi przez OllamaProvider: {e}")
            raise

    async def check_health(self) -> bool:
        """Sprawdza dostępność serwera Ollama wysyłając zapytanie GET /api/tags."""
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except Exception:
            return False
