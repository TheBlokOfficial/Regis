"""Singleton-router należący do `ai.llm` — jedyny obiekt LLM, jaki trzyma Kernel
(`agent/engine.py`). Nie jest konkretnym dostawcą: przy każdym wywołaniu
rozwiązuje aktualnie aktywny backend przez `BackendRegistry`, więc zmiana
aktywnego dostawcy (`PUT /api/v1/llm/providers/active`) działa natychmiast,
bez mutowania stanu Kernela z zewnątrz."""

from __future__ import annotations

from typing import Any, AsyncIterator

from server.agent.llm import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition
from server.ai.llm.registry import BackendRegistry


class LLMRouter(BaseLLMProvider):
    """Rozwiązuje aktywny `BaseLLMProvider` na nowo tylko gdy zmieni się aktywne ID
    (`BackendRegistry.get_active_backend_id()`) — unika zbędnego I/O na dysku przy
    każdym fragmencie strumienia w obrębie tej samej tury."""

    def __init__(self, registry: BackendRegistry) -> None:
        self._registry = registry
        self._cached_active_id: str | None = None
        self._cached_provider: BaseLLMProvider | None = None

    async def _resolve(self) -> BaseLLMProvider:
        active_id = await self._registry.get_active_backend_id()
        if self._cached_provider is None or active_id != self._cached_active_id:
            self._cached_provider = await self._registry.get_active_provider()
            self._cached_active_id = active_id
        return self._cached_provider

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | ToolCallRequest]:
        provider = await self._resolve()
        async for event in provider.generate_stream(messages, tools=tools, **kwargs):
            yield event

    async def check_health(self) -> bool:
        provider = await self._resolve()
        return await provider.check_health()
