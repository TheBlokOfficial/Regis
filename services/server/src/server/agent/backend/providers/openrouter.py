import json
from typing import Any, AsyncIterator
import httpx
from shared import get_logger
from server.config import load_settings
from server.agent.backend.providers.base import BaseLLMProvider, LLMMessage

logger = get_logger("regis.agent.providers.openrouter")


class OpenRouterProvider(BaseLLMProvider):
    """Dostawca LLM dla usługi OpenRouter API (REST API ze strumieniowaniem SSE)."""

    BASE_URL = "https://openrouter.ai/api/v1"

    def __init__(
        self,
        api_key: str = "",
        model: str = "anthropic/claude-3.5-sonnet",
        max_tokens: int | None = None,
    ) -> None:
        self.api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self.base_url = self.BASE_URL

    @property
    def model(self) -> str:
        return self._model

    @property
    def max_tokens(self) -> int | None:
        return self._max_tokens

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/TheBlokOfficial/Regis",
            "X-Title": "Regis OS",
        }

        payload = {
            "model": kwargs.get("model", self._model),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
        }

        max_t = kwargs.get("max_tokens", self._max_tokens)
        if max_t is not None:
            payload["max_tokens"] = max_t

        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]

        logger.debug(f"Strumieniowanie z OpenRouter [{url}] (model: '{payload['model']}')...")

        timeout_val = load_settings().llm_timeout
        httpx_timeout = httpx.Timeout(timeout_val, connect=5.0)

        try:
            in_thinking = False
            async with httpx.AsyncClient(timeout=httpx_timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or not line.startswith("data: "):
                            continue

                        raw_data = line[6:]
                        if raw_data == "[DONE]":
                            break

                        try:
                            data = json.loads(raw_data)
                            choices = data.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                reasoning = (
                                    delta.get("reasoning")
                                    or delta.get("reasoning_content")
                                    or delta.get("thinking")
                                )
                                content = delta.get("content", "")

                                if reasoning:
                                    if not in_thinking:
                                        yield "<think>\n"
                                        in_thinking = True
                                    yield reasoning
                                elif content:
                                    if in_thinking:
                                        yield "\n</think>\n\n"
                                        in_thinking = False
                                    yield content
                        except json.JSONDecodeError:
                            continue

                    if in_thinking:
                        yield "\n</think>\n\n"
        except httpx.HTTPStatusError as e:
            logger.error(f"Błąd HTTP OpenRouter API [{e.response.status_code}]: {e.response.text}")
            raise RuntimeError(f"Błąd OpenRouter API HTTP {e.response.status_code}: {e.response.text}") from e
        except httpx.ReadTimeout as e:
            logger.error(f"Przekroczono limit czasu oczekiwania na tokeny ({timeout_val}s) z OpenRouter.")
            raise RuntimeError(f"Timeout strumienia z OpenRouter ({timeout_val}s): {e}") from e
        except Exception as e:
            logger.error(f"Błąd podczas strumieniowania odpowiedzi przez OpenRouterProvider: {e}")
            raise

    async def check_health(self) -> bool:
        """Sprawdza dostępność dostawcy OpenRouter (weryfikacja czy podano klucz API)."""
        if not self.api_key:
            logger.debug("Healthcheck OpenRouter: brak skonfigurowanego klucza API.")
            return False
        return True
