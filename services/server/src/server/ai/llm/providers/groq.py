import json
from typing import Any, AsyncIterator
import httpx
from shared import get_logger
from server.config import load_settings
from server.agent.llm import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition

logger = get_logger("regis.ai.llm.providers.groq")


def _messages_to_openai_payload(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Mapuje LLMMessage na format wiadomości OpenAI-compatible (w tym role 'tool' i tool_calls).
    Identyczne z `openrouter.py` — Groq to również OpenAI-compatible REST API."""
    payload_messages: list[dict[str, Any]] = []
    for m in messages:
        entry: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.role == "assistant" and m.tool_calls:
            entry["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
                }
                for call in m.tool_calls
            ]
        if m.role == "tool":
            entry["tool_call_id"] = m.tool_call_id
        payload_messages.append(entry)
    return payload_messages


def _tools_to_openai_payload(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Mapuje ToolDefinition na format 'tools' OpenAI-compatible."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }
        for tool in tools
    ]


class GroqProvider(BaseLLMProvider):
    """Dostawca LLM dla usługi Groq (REST API ze strumieniowaniem SSE,
    OpenAI-compatible — endpoint i format zweryfikowane bezpośrednio w
    dokumentacji Groq, nie zgadywane). W odróżnieniu od `OpenRouterProvider`
    bez pola `reasoning`/nagłówków `HTTP-Referer`/`X-Title` — to rozszerzenia
    specyficzne dla OpenRouter, nieudokumentowane w API Groq."""

    BASE_URL = "https://api.groq.com/openai/v1"

    def __init__(
        self,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
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
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | ToolCallRequest]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._model),
            "messages": _messages_to_openai_payload(messages),
            "stream": True,
        }

        if tools:
            payload["tools"] = _tools_to_openai_payload(tools)

        max_t = kwargs.get("max_tokens", self._max_tokens)
        if max_t is not None:
            payload["max_tokens"] = max_t

        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]

        logger.debug(f"Strumieniowanie z Groq [{url}] (model: '{payload['model']}')...")

        timeout_val = load_settings().llm_timeout
        httpx_timeout = httpx.Timeout(timeout_val, connect=5.0)

        try:
            in_thinking = False
            # Bufor akumulujący fragmentaryczne delty tool_calls po indeksie (OpenAI-compatible SSE
            # przysyła argumenty wywołania narzędzia porcjami — dopiero cały strumień daje poprawny JSON).
            pending_tool_calls: dict[int, dict[str, Any]] = {}
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
                                delta_tool_calls = delta.get("tool_calls")

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

                                if delta_tool_calls:
                                    for call_delta in delta_tool_calls:
                                        idx = call_delta.get("index", 0)
                                        entry = pending_tool_calls.setdefault(
                                            idx, {"id": "", "name": "", "arguments": ""}
                                        )
                                        if call_delta.get("id"):
                                            entry["id"] = call_delta["id"]
                                        function_delta = call_delta.get("function", {})
                                        if function_delta.get("name"):
                                            entry["name"] = function_delta["name"]
                                        if function_delta.get("arguments"):
                                            entry["arguments"] += function_delta["arguments"]
                        except json.JSONDecodeError:
                            continue

                    if in_thinking:
                        yield "\n</think>\n\n"

                    for entry in pending_tool_calls.values():
                        try:
                            arguments = json.loads(entry["arguments"]) if entry["arguments"] else {}
                        except json.JSONDecodeError:
                            logger.error(f"Nie udało się zdekodować argumentów narzędzia: {entry['arguments']}")
                            arguments = {}
                        yield ToolCallRequest(id=entry["id"], name=entry["name"], arguments=arguments)
        except httpx.HTTPStatusError as e:
            logger.error(f"Błąd HTTP Groq API [{e.response.status_code}]: {e.response.text}")
            raise RuntimeError(f"Błąd Groq API HTTP {e.response.status_code}: {e.response.text}") from e
        except httpx.ReadTimeout as e:
            logger.error(f"Przekroczono limit czasu oczekiwania na tokeny ({timeout_val}s) z Groq.")
            raise RuntimeError(f"Timeout strumienia z Groq ({timeout_val}s): {e}") from e
        except Exception as e:
            logger.error(f"Błąd podczas strumieniowania odpowiedzi przez GroqProvider: {e}")
            raise

    async def check_health(self) -> bool:
        """Sprawdza dostępność dostawcy Groq (weryfikacja czy podano klucz API)."""
        if not self.api_key:
            logger.debug("Healthcheck Groq: brak skonfigurowanego klucza API.")
            return False
        return True
