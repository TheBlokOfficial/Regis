import json
from typing import Any, AsyncIterator

import httpx
from shared import get_logger

from server.config import load_settings
from server.ports.llm import BaseLLMProvider, LLMMessage, ReasoningChunk, ToolCallRequest, ToolDefinition

logger = get_logger("regis.ai.llm.providers.openai_compatible")


def _messages_to_openai_payload(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Mapuje LLMMessage na format wiadomości OpenAI-compatible (w tym role 'tool' i tool_calls)."""
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


class OpenAICompatibleProvider(BaseLLMProvider):
    """Dostawca LLM dla dowolnego REST API zgodnego z formatem OpenAI Chat
    Completions (REST + strumieniowanie SSE) — scalenie dawnych, niemal
    identycznych `OpenRouterProvider`/`GroqProvider` (różniły się wyłącznie
    `base_url`, domyślnym modelem i garścią rozszerzeń specyficznych dla
    OpenRouter). `extra_headers`/`extra_payload` pozwalają dostawcy na
    konkretny typ (patrz `ai/llm/factory.py::LLMFactory.create_provider`)
    dołożyć własne, niestandardowe rozszerzenia bez tworzenia osobnej klasy —
    np. OpenRouter dokłada nagłówki `HTTP-Referer`/`X-Title` i pole payloadu
    `reasoning`, których Groq nie rozumie."""

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        model: str = "",
        max_tokens: int | None = None,
        extra_headers: dict[str, str] | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._model = model
        self._max_tokens = max_tokens
        self._extra_headers = extra_headers or {}
        self._extra_payload = extra_payload or {}

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
    ) -> AsyncIterator[str | ReasoningChunk | ToolCallRequest]:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._model),
            "messages": _messages_to_openai_payload(messages),
            "stream": True,
            **self._extra_payload,
        }

        if tools:
            payload["tools"] = _tools_to_openai_payload(tools)

        max_t = kwargs.get("max_tokens", self._max_tokens)
        if max_t is not None:
            payload["max_tokens"] = max_t

        if "temperature" in kwargs:
            payload["temperature"] = kwargs["temperature"]

        logger.debug(f"Strumieniowanie z [{url}] (model: '{payload['model']}')...")

        timeout_val = load_settings().llm_timeout
        httpx_timeout = httpx.Timeout(timeout_val, connect=5.0)

        try:
            # Bufor akumulujący fragmentaryczne delty tool_calls po indeksie (OpenAI-compatible SSE
            # przysyła argumenty wywołania narzędzia porcjami — dopiero cały strumień daje poprawny JSON).
            pending_tool_calls: dict[int, dict[str, Any]] = {}
            async with httpx.AsyncClient(timeout=httpx_timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.is_error:
                        # Treść trzeba doczytać TU, w środku `async with client.stream(...)` — po
                        # wyjściu z tego bloku httpx zamyka połączenie i dalszy odczyt jest już
                        # niemożliwy (stąd poprzednia wersja tego kodu gubiła treść błędu API).
                        body_bytes = await response.aread()
                        body_text = body_bytes.decode("utf-8", errors="replace")
                        logger.error(
                            f"Błąd HTTP dostawcy OpenAI-compatible [{self.base_url}] "
                            f"[{response.status_code}]: {body_text}"
                        )
                        raise RuntimeError(f"Błąd API [{self.base_url}] HTTP {response.status_code}: {body_text}")

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

                                # Rozumowanie i odpowiedź to dwa różne typy zdarzenia, nie
                                # jeden string ze znacznikiem — patrz `ReasoningChunk`.
                                if reasoning:
                                    yield ReasoningChunk(text=reasoning)
                                elif content:
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

                    for entry in pending_tool_calls.values():
                        try:
                            arguments = json.loads(entry["arguments"]) if entry["arguments"] else {}
                        except json.JSONDecodeError:
                            logger.error(f"Nie udało się zdekodować argumentów narzędzia: {entry['arguments']}")
                            arguments = {}
                        yield ToolCallRequest(id=entry["id"], name=entry["name"], arguments=arguments)
        except httpx.ReadTimeout as e:
            logger.error(f"Przekroczono limit czasu oczekiwania na tokeny ({timeout_val}s) z [{self.base_url}].")
            raise RuntimeError(f"Timeout strumienia z [{self.base_url}] ({timeout_val}s): {e}") from e
        except RuntimeError:
            # Już zalogowane wyżej (błąd HTTP z treścią odpowiedzi) — nie duplikować logu.
            raise
        except Exception as e:
            logger.error(f"Błąd podczas strumieniowania odpowiedzi przez OpenAICompatibleProvider [{self.base_url}]: {e}")
            raise
