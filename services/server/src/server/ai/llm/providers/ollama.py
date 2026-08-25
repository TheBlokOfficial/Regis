import json
import uuid
from typing import Any, AsyncIterator

import httpx
from shared import get_logger

from server.config import load_settings
from server.ports.llm import (
    BaseLLMProvider,
    GenerationUsage,
    LLMMessage,
    ReasoningChunk,
    ToolCallRequest,
    ToolDefinition,
)

logger = get_logger("regis.ai.llm.providers.ollama")


def _messages_to_ollama_payload(messages: list[LLMMessage]) -> list[dict[str, Any]]:
    """Mapuje LLMMessage na format wiadomości Ollama /api/chat (w tym rolę 'tool')."""
    payload_messages: list[dict[str, Any]] = []
    for m in messages:
        entry: dict[str, Any] = {"role": m.role, "content": m.content}
        if m.role == "assistant" and m.tool_calls:
            entry["tool_calls"] = [
                {"function": {"name": call.name, "arguments": call.arguments}} for call in m.tool_calls
            ]
        if m.role == "tool" and m.tool_name:
            entry["tool_name"] = m.tool_name
        payload_messages.append(entry)
    return payload_messages


def _tools_to_ollama_payload(tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Mapuje ToolDefinition na format 'tools' Ollamy (identyczny kształt co OpenAI-compatible)."""
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


class OllamaProvider(BaseLLMProvider):
    """Dostawca LLM komunikujący się z lokalnym serwerem Ollama (REST API ze strumieniowaniem)."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        max_tokens: int | None = None,
        options: dict[str, Any] | None = None,
        think: bool | str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._model = model
        self._max_tokens = max_tokens
        # Ollama trzyma parametry generacji w zagnieżdżonym worku `options`, a `think`
        # (bool albo poziom "low"/"medium"/"high"/"max") na najwyższym poziomie —
        # składa je fabryka z presetu, patrz `ai/llm/factory.py`.
        self._options = options or {}
        self._think = think

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
    ) -> AsyncIterator[str | ReasoningChunk | ToolCallRequest | GenerationUsage]:
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {
            "model": kwargs.get("model", self._model),
            "messages": _messages_to_ollama_payload(messages),
            "stream": True,
        }

        if tools:
            payload["tools"] = _tools_to_ollama_payload(tools)

        options = {**self._options, **kwargs.get("options", {})}
        max_t = kwargs.get("max_tokens", self._max_tokens)
        if max_t is not None and "num_predict" not in options:
            options["num_predict"] = max_t

        if options:
            payload["options"] = options

        think = kwargs.get("think", self._think)
        if think is not None:
            payload["think"] = think

        logger.debug(f"Strumieniowanie z Ollamy [{url}] (model: '{payload['model']}')...")

        timeout_val = load_settings().llm_timeout
        httpx_timeout = httpx.Timeout(timeout_val, connect=5.0)

        try:
            # Ollama nie ma osobnego chunka `usage` jak rodzina OpenAI-compatible —
            # liczniki i powód zakończenia przychodzą w tym samym, ostatnim komunikacie
            # oznaczonym `done: true`. Pojęcia cache promptu nie zna w ogóle, więc
            # `cached_tokens` zostaje `None` (patrz `GenerationUsage`).
            usage: GenerationUsage | None = None
            async with httpx.AsyncClient(timeout=httpx_timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("done"):
                                usage = GenerationUsage(
                                    prompt_tokens=data.get("prompt_eval_count"),
                                    completion_tokens=data.get("eval_count"),
                                    cached_tokens=None,
                                    finish_reason=data.get("done_reason"),
                                    model=data.get("model") or payload["model"],
                                )
                            message_data = data.get("message", {})
                            reasoning = (
                                message_data.get("reasoning_content")
                                or message_data.get("thinking")
                                or message_data.get("reasoning")
                            )
                            content = message_data.get("content", "")
                            raw_tool_calls = message_data.get("tool_calls")

                            # Rozumowanie i odpowiedź to dwa różne typy zdarzenia, nie
                            # jeden string ze znacznikiem — patrz `ReasoningChunk`.
                            if reasoning:
                                yield ReasoningChunk(text=reasoning)
                            elif content:
                                yield content

                            if raw_tool_calls:
                                # Ollama nie fragmentuje tool_calls w streamie — przychodzą kompletne
                                # w jednym komunikacie message, bez potrzeby buforowania.
                                for call in raw_tool_calls:
                                    function_data = call.get("function", {})
                                    yield ToolCallRequest(
                                        id=call.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                                        name=function_data.get("name", ""),
                                        arguments=function_data.get("arguments", {}) or {},
                                    )
                        except json.JSONDecodeError:
                            continue

                    yield usage or GenerationUsage(model=payload["model"])
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
