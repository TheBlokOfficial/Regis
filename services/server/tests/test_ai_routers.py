"""Testy singletonów-routerów `server.ai.{llm,stt,tts}` — sam mechanizm
rozwiązywania/cache'owania aktywnego konkretu, niezależnie od realnych API
(Ollama/OpenRouter/Groq/ElevenLabs)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest

from server.agent.llm import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition
from server.ai.llm.router import LLMRouter
from server.ai.stt.router import STTRouter
from server.ai.stt.providers import MockSTTProvider
from server.ai.tts.router import TTSRouter
from server.ai.tts.providers import MockTTSProvider


class _FakeProvider(BaseLLMProvider):
    """Konkret-atrapa — tożsamość (`id(self)`) pozwala zweryfikować, który obiekt
    faktycznie obsłużył wywołanie, bez wołania prawdziwego API."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | ToolCallRequest]:
        yield self.name

    async def check_health(self) -> bool:
        return True


class _FakeRegistry:
    """Duck-typowany `BackendRegistry` — liczy wywołania `get_active_provider()`,
    żeby zweryfikować, że `LLMRouter` cache'uje, dopóki `active_id` się nie zmieni."""

    def __init__(self) -> None:
        self.active_id = "bk_a"
        self.providers = {"bk_a": _FakeProvider("A"), "bk_b": _FakeProvider("B")}
        self.get_active_provider_calls = 0

    async def get_active_backend_id(self) -> str:
        return self.active_id

    async def get_active_provider(self) -> _FakeProvider:
        self.get_active_provider_calls += 1
        return self.providers[self.active_id]


@pytest.mark.anyio
async def test_llm_router_delegates_to_active_provider():
    registry = _FakeRegistry()
    router = LLMRouter(registry)

    chunks = [c async for c in router.generate_stream([LLMMessage(role="user", content="hi")])]
    assert chunks == ["A"]


@pytest.mark.anyio
async def test_llm_router_switches_after_active_id_changes():
    registry = _FakeRegistry()
    router = LLMRouter(registry)

    first = [c async for c in router.generate_stream([LLMMessage(role="user", content="hi")])]
    registry.active_id = "bk_b"
    second = [c async for c in router.generate_stream([LLMMessage(role="user", content="hi")])]

    assert first == ["A"]
    assert second == ["B"]


@pytest.mark.anyio
async def test_llm_router_caches_provider_while_active_id_unchanged():
    registry = _FakeRegistry()
    router = LLMRouter(registry)

    async for _ in router.generate_stream([LLMMessage(role="user", content="hi")]):
        pass
    async for _ in router.generate_stream([LLMMessage(role="user", content="hi")]):
        pass

    assert registry.get_active_provider_calls == 1


class _FakeSTTRegistry:
    """Duck-typowany `STTRegistry` — mirror `_FakeRegistry` (LLM), liczy wywołania
    `get_active_provider()`."""

    def __init__(self) -> None:
        self.active_id = "stt_a"
        self.providers = {"stt_a": MockSTTProvider("A"), "stt_b": MockSTTProvider("B")}
        self.options = {"stt_a": {"marker": "a"}, "stt_b": {"marker": "b"}}
        self.get_active_provider_calls = 0

    async def get_active_backend_id(self) -> str:
        return self.active_id

    async def load_all_instances(self) -> dict[str, SimpleNamespace]:
        return {bid: SimpleNamespace(options=opts) for bid, opts in self.options.items()}

    async def get_active_provider(self) -> MockSTTProvider:
        self.get_active_provider_calls += 1
        return self.providers[self.active_id]


class _FakeTTSRegistry:
    """Duck-typowany `TTSRegistry` — mirror `_FakeRegistry` (LLM)."""

    def __init__(self) -> None:
        self.active_id = "tts_a"
        self.providers = {"tts_a": MockTTSProvider(), "tts_b": MockTTSProvider()}
        self.options = {"tts_a": {"marker": "a"}, "tts_b": {"marker": "b"}}
        self.get_active_provider_calls = 0

    async def get_active_backend_id(self) -> str:
        return self.active_id

    async def load_all_instances(self) -> dict[str, SimpleNamespace]:
        return {bid: SimpleNamespace(options=opts) for bid, opts in self.options.items()}

    async def get_active_provider(self) -> MockTTSProvider:
        self.get_active_provider_calls += 1
        return self.providers[self.active_id]


@pytest.mark.anyio
async def test_stt_router_delegates_to_active_provider():
    registry = _FakeSTTRegistry()
    router = STTRouter(registry)

    result = await router.transcribe(b"\x00\x00")
    assert result == "A"


@pytest.mark.anyio
async def test_stt_router_switches_after_active_id_changes():
    registry = _FakeSTTRegistry()
    router = STTRouter(registry)

    first = await router.transcribe(b"\x00\x00")
    registry.active_id = "stt_b"
    second = await router.transcribe(b"\x00\x00")

    assert first == "A"
    assert second == "B"


@pytest.mark.anyio
async def test_stt_router_caches_provider_while_active_id_unchanged():
    registry = _FakeSTTRegistry()
    router = STTRouter(registry)

    await router.transcribe(b"\x00\x00")
    await router.transcribe(b"\x00\x00")

    assert registry.get_active_provider_calls == 1


@pytest.mark.anyio
async def test_stt_router_rebuilds_when_active_instance_options_change_in_place():
    """Regresja: shim `PUT /providers/config` edytuje `options` aktywnej instancji
    (`STTRegistry.update_instance`) bez zmiany jej ID — cache musi to wykryć,
    nie tylko zmianę `active_id`."""
    registry = _FakeSTTRegistry()
    router = STTRouter(registry)

    await router.transcribe(b"\x00\x00")
    registry.options["stt_a"] = {"marker": "changed"}
    await router.transcribe(b"\x00\x00")

    assert registry.get_active_provider_calls == 2


@pytest.mark.anyio
async def test_stt_router_reports_active_provider_class_name():
    router = STTRouter(_FakeSTTRegistry())
    assert await router.get_active_provider_class_name() == "MockSTTProvider"


@pytest.mark.anyio
async def test_tts_router_delegates_to_active_provider():
    registry = _FakeTTSRegistry()
    router = TTSRouter(registry)

    audio = await router.synthesize("cześć")
    assert isinstance(audio, bytes) and len(audio) > 0


@pytest.mark.anyio
async def test_tts_router_caches_provider_while_active_id_unchanged():
    registry = _FakeTTSRegistry()
    router = TTSRouter(registry)

    await router.synthesize("a")
    await router.synthesize("b")

    assert registry.get_active_provider_calls == 1


@pytest.mark.anyio
async def test_tts_router_rebuilds_when_active_instance_options_change_in_place():
    registry = _FakeTTSRegistry()
    router = TTSRouter(registry)

    await router.synthesize("a")
    registry.options["tts_a"] = {"marker": "changed"}
    await router.synthesize("a")

    assert registry.get_active_provider_calls == 2


@pytest.mark.anyio
async def test_tts_router_reports_active_provider_class_name():
    router = TTSRouter(_FakeTTSRegistry())
    assert await router.get_active_provider_class_name() == "MockTTSProvider"
