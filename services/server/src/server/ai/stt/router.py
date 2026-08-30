"""Singleton-router należący do `ai.stt` — jedyny obiekt STT, jaki trzyma
`voice/session.py`. Przy każdym wywołaniu rozwiązuje aktualnie aktywną
instancję przez `STTRegistry` (mirror `ai.llm.router.LLMRouter`), więc
`PUT /api/v1/voice/stt/providers/active` (albo shim `PUT
/api/v1/voice/providers/config`) działa od razu, bez restartu serwera.

Cache klucz to `(active_id, options)`, nie sam `active_id`: `PUT
.../stt/providers/{id}` nadpisuje `options` aktywnej instancji w miejscu
(`STTRegistry.update_instance`), więc sam niezmieniony `active_id` nie
gwarantuje niezmienionej konfiguracji. Ten sam klucz ma dziś `LLMRouter` —
dawna uwaga „w odróżnieniu od LLM" przestała być prawdziwa, gdy LLM też
dostał edycję presetu w miejscu."""

from __future__ import annotations

from typing import Any

from server.ai.stt.registry import STTRegistry
from server.ports.stt import BaseSTTProvider


class STTRouter(BaseSTTProvider):
    def __init__(self, registry: STTRegistry) -> None:
        self._registry = registry
        self._cached_active_id: str | None = None
        self._cached_options: dict[str, Any] | None = None
        self._cached_provider: BaseSTTProvider | None = None

    async def _resolve(self) -> BaseSTTProvider:
        active_id = await self._registry.get_active_backend_id()
        # `.get()`, nie `[...]` — wskaźnik aktywnego ID może wskazywać na plik
        # skasowany z dysku poza aplikacją; awaryjne przełączenie na pierwszą
        # dostępną instancję należy do rejestru, nie tutaj.
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

    async def transcribe(self, pcm_audio: bytes) -> str:
        provider = await self._resolve()
        return await provider.transcribe(pcm_audio)

    async def get_active_provider_class_name(self) -> str:
        provider = await self._resolve()
        return type(provider).__name__

    async def is_active_provider_placeholder(self) -> bool:
        provider = await self._resolve()
        return provider.is_placeholder
