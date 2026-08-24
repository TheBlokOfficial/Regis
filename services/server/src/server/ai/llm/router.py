"""Singleton-router należący do `ai.llm` — jedyny obiekt LLM, jaki trzyma Kernel
(`agent/engine.py`). Nie jest konkretnym dostawcą: przy każdym wywołaniu
rozwiązuje aktualnie aktywny backend przez `BackendRegistry`, więc zmiana
aktywnego dostawcy (`PUT /api/v1/llm/providers/active`) działa natychmiast,
bez mutowania stanu Kernela z zewnątrz."""

from __future__ import annotations

from typing import Any, AsyncIterator

from server.agent.llm import BaseLLMProvider, LLMMessage, ReasoningChunk, ToolCallRequest, ToolDefinition
from server.ai.llm.registry import BackendRegistry


class LLMRouter(BaseLLMProvider):
    """Rozwiązuje aktywnego `BaseLLMProvider` na nowo, gdy zmieni się aktywne ID
    **albo opcje aktywnej instancji** — unikając przy tym zbędnego I/O na dysku
    przy każdym fragmencie strumienia w obrębie tej samej tury.

    Klucz cache to `(active_id, options)`, nie sam `active_id`. Wcześniejsza wersja
    patrzyła wyłącznie na ID, opierając się na założeniu „REST nigdy nie edytuje
    pól istniejącej instancji, tylko create/switch/delete". Założenie przestało
    być prawdziwe wraz z `PUT /api/v1/llm/providers/{id}`: edycja modelu albo
    klucza API **aktywnego** presetu zapisywała się na dysk i potwierdzała w UI,
    a agent do restartu serwera używał starej konfiguracji. `STTRouter`/`TTSRouter`
    miały ten sam problem naprawiony wcześniej — tu jest ta sama poprawka.
    """

    def __init__(self, registry: BackendRegistry) -> None:
        self._registry = registry
        self._cached_active_id: str | None = None
        self._cached_options: dict[str, Any] | None = None
        self._cached_provider: BaseLLMProvider | None = None

    async def _resolve(self) -> BaseLLMProvider:
        active_id = await self._registry.get_active_backend_id()
        # `.get()`, nie `[...]` — wskaźnik aktywnego ID może wskazywać na plik
        # skasowany z dysku poza aplikacją; awaryjne przełączenie na pierwszą
        # dostępną instancję należy do rejestru (`get_active_provider`), a nie tutaj.
        active_instance = (await self._registry.load_all_instances()).get(active_id)
        active_options = active_instance.options if active_instance is not None else None
        if (
            self._cached_provider is None
            or active_id != self._cached_active_id
            or active_options != self._cached_options
        ):
            self._cached_provider = await self._registry.get_active_provider()
            self._cached_active_id = active_id
            self._cached_options = active_options
        return self._cached_provider

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | ReasoningChunk | ToolCallRequest]:
        provider = await self._resolve()
        async for event in provider.generate_stream(messages, tools=tools, **kwargs):
            yield event
