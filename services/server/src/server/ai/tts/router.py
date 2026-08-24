"""Singleton-router należący do `ai.tts` — jedyny obiekt TTS, jaki trzyma
`voice/session.py`. Przy każdym wywołaniu rozwiązuje aktualnie aktywną
instancję przez `TTSRegistry` (mirror `ai.llm.router.LLMRouter`), więc
`PUT /api/v1/voice/tts/providers/active` (albo shim `PUT
/api/v1/voice/providers/config`) działa od razu, bez restartu serwera.

Cache klucz to `(active_id, options)`, nie sam `active_id` — w odróżnieniu od
LLM (gdzie REST nigdy nie edytuje pól istniejącej instancji, tylko
create/switch/delete), shim kompatybilności potrafi nadpisać `options`
aktywnej instancji w miejscu (`TTSRegistry.update_instance`), więc sam
niezmieniony `active_id` nie gwarantuje niezmienionej konfiguracji."""

from __future__ import annotations

from typing import Any, AsyncIterator

from server.ai.tts.registry import TTSRegistry
from server.voice.tts import BaseTTSProvider


class TTSRouter(BaseTTSProvider):
    def __init__(self, registry: TTSRegistry) -> None:
        self._registry = registry
        self._cached_active_id: str | None = None
        self._cached_options: dict[str, Any] | None = None
        self._cached_provider: BaseTTSProvider | None = None

    async def _resolve(self) -> BaseTTSProvider:
        active_id = await self._registry.get_active_backend_id()
        active_options = (await self._registry.load_all_instances())[active_id].options
        if (
            self._cached_provider is None
            or active_id != self._cached_active_id
            or active_options != self._cached_options
        ):
            self._cached_provider = await self._registry.get_active_provider()
            self._cached_active_id = active_id
            self._cached_options = active_options
        return self._cached_provider

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        provider = await self._resolve()
        async for chunk in provider.synthesize_stream(text):
            yield chunk

    async def get_active_provider_class_name(self) -> str:
        provider = await self._resolve()
        return type(provider).__name__
