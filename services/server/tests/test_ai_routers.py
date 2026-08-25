"""Testy singletonów-routerów `server.ai.{llm,stt,tts}` — sam mechanizm
rozwiązywania/cache'owania aktywnego konkretu, niezależnie od realnych API
(Ollama/OpenRouter/Groq/ElevenLabs)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest
from server.ai.llm.circuit_breaker import CircuitBreaker
from server.ai.llm.router import LLMRouter
from server.ai.llm.token_budget import TokenBudgetTracker
from server.ai.stt.providers import MockSTTProvider
from server.ai.stt.router import STTRouter
from server.ai.tts.providers import MockTTSProvider
from server.ai.tts.router import TTSRouter
from server.ports.llm import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition


class _FakeProvider(BaseLLMProvider):
    """Konkret-atrapa — tożsamość (`id(self)`) pozwala zweryfikować, który obiekt
    faktycznie obsłużył wywołanie, bez wołania prawdziwego API. `fail_before_yield`
    symuluje błąd HTTP zwrócony przed pierwszym fragmentem strumienia (jak realny
    429 Groq — patrz `openai_compatible.py`), `fail_after_yield` symuluje błąd
    w środku już rozpoczętej odpowiedzi."""

    def __init__(self, name: str, fail_before_yield: bool = False, fail_after_yield: bool = False) -> None:
        self.name = name
        self.fail_before_yield = fail_before_yield
        self.fail_after_yield = fail_after_yield
        self.call_count = 0

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | ToolCallRequest]:
        self.call_count += 1
        if self.fail_before_yield:
            raise RuntimeError(f"Błąd API [{self.name}] HTTP 429: rate_limit_exceeded, try again in 0.01s")
        yield self.name
        if self.fail_after_yield:
            raise RuntimeError(f"Błąd API [{self.name}] HTTP 500: ucięty w środku")


class _FakeRegistry:
    """Duck-typowany `BackendRegistry` — liczy wywołania `create_provider_instance()`,
    żeby zweryfikować, że `LLMRouter` cache'uje, dopóki wybrany preset (ID **i**
    jego opcje) się nie zmieni. `chain` mirror'uje `get_fallback_chain()`."""

    def __init__(self) -> None:
        self.active_id = "bk_a"
        self.providers = {"bk_a": _FakeProvider("A"), "bk_b": _FakeProvider("B")}
        self.options: dict[str, dict[str, Any]] = {"bk_a": {"marker": "a"}, "bk_b": {"marker": "b"}}
        self.chain: list[str] = []
        self.create_provider_instance_calls = 0

    async def get_active_backend_id(self) -> str:
        return self.active_id

    async def get_fallback_chain(self) -> list[str]:
        return self.chain

    async def load_all_instances(self) -> dict[str, SimpleNamespace]:
        return {bid: SimpleNamespace(id=bid, options=opts) for bid, opts in self.options.items()}

    def create_provider_instance(self, instance: SimpleNamespace) -> _FakeProvider:
        self.create_provider_instance_calls += 1
        return self.providers[instance.id]


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

    assert registry.create_provider_instance_calls == 1


@pytest.mark.anyio
async def test_llm_router_rebuilds_when_active_instance_options_change_in_place():
    """Regresja: `PUT /api/v1/llm/providers/{id}` edytuje `options` aktywnego presetu
    (`BackendRegistry.update_instance`) bez zmiany jego ID — cache musi to wykryć.

    Wcześniej klucz cache to był sam `active_id`, opierając się na nieaktualnym już
    założeniu, że REST nigdy nie edytuje pól istniejącej instancji. Skutek na żywo:
    zmiana modelu albo klucza API aktywnego presetu zapisywała się na dysk i była
    potwierdzana w UI, a agent do restartu serwera używał starej konfiguracji.
    Lustro `test_stt_router_rebuilds_when_active_instance_options_change_in_place`."""
    registry = _FakeRegistry()
    router = LLMRouter(registry)

    async for _ in router.generate_stream([LLMMessage(role="user", content="hi")]):
        pass
    registry.options["bk_a"] = {"marker": "changed"}
    async for _ in router.generate_stream([LLMMessage(role="user", content="hi")]):
        pass

    assert registry.create_provider_instance_calls == 2


@pytest.mark.anyio
async def test_llm_router_falls_back_when_active_provider_fails_before_first_chunk():
    """Rdzeń łańcucha fallbacku: kandydat 1 pada z błędem PRZED pierwszym fragmentem
    (jak realny 429 Groq) — router bez opóźnienia próbuje kandydata 2 z łańcucha."""
    registry = _FakeRegistry()
    registry.providers["bk_a"] = _FakeProvider("A", fail_before_yield=True)
    registry.chain = ["bk_a", "bk_b"]
    router = LLMRouter(registry)

    chunks = [c async for c in router.generate_stream([LLMMessage(role="user", content="hi")])]

    assert chunks == ["B"]


@pytest.mark.anyio
async def test_llm_router_does_not_switch_after_first_chunk_already_yielded():
    """Zasada bezpieczeństwa: raz rozpoczęta odpowiedź nigdy nie jest cicho zamieniana
    na innego kandydata, nawet jeśli kolejny błąd padnie w środku strumienia."""
    registry = _FakeRegistry()
    registry.providers["bk_a"] = _FakeProvider("A", fail_after_yield=True)
    registry.chain = ["bk_a", "bk_b"]
    router = LLMRouter(registry)

    with pytest.raises(RuntimeError, match="HTTP 500"):
        async for _ in router.generate_stream([LLMMessage(role="user", content="hi")]):
            pass


@pytest.mark.anyio
async def test_llm_router_circuit_breaker_skips_tripped_candidate_on_next_turn():
    """Po jednym złapanym błędzie breaker pomija tego kandydata w kolejnej turze —
    unika ponownego, zbędnego round-tripu do dostawcy, który i tak odrzuci."""
    registry = _FakeRegistry()
    provider_a = _FakeProvider("A", fail_before_yield=True)
    registry.providers["bk_a"] = provider_a
    registry.chain = ["bk_a", "bk_b"]
    router = LLMRouter(registry, breaker=CircuitBreaker(default_cooldown_seconds=60.0))

    async for _ in router.generate_stream([LLMMessage(role="user", content="hi")]):
        pass
    async for _ in router.generate_stream([LLMMessage(role="user", content="hi")]):
        pass

    assert provider_a.call_count == 1


@pytest.mark.anyio
async def test_llm_router_token_budget_skips_candidate_without_headroom():
    """Preset z `tpm_limit` w opcjach jest pomijany, gdy tracker już odnotował zużycie
    bliskie limitu — bez czekania na realny 429."""
    registry = _FakeRegistry()
    registry.options["bk_a"] = {"marker": "a", "tpm_limit": 100}
    registry.chain = ["bk_a", "bk_b"]
    tracker = TokenBudgetTracker()
    tracker.record("bk_a", 90)
    router = LLMRouter(registry, tracker=tracker)

    chunks = [c async for c in router.generate_stream([LLMMessage(role="user", content="x" * 100)])]

    assert chunks == ["B"]
    assert registry.providers["bk_a"].call_count == 0


@pytest.mark.anyio
async def test_llm_router_raises_when_all_candidates_fail():
    registry = _FakeRegistry()
    registry.providers["bk_a"] = _FakeProvider("A", fail_before_yield=True)
    registry.providers["bk_b"] = _FakeProvider("B", fail_before_yield=True)
    registry.chain = ["bk_a", "bk_b"]
    router = LLMRouter(registry)

    with pytest.raises(RuntimeError, match="HTTP 429"):
        async for _ in router.generate_stream([LLMMessage(role="user", content="hi")]):
            pass


@pytest.mark.anyio
async def test_llm_router_empty_chain_falls_back_to_single_active_id():
    """Pusty łańcuch (stan domyślny) = zachowanie nierozróżnialne od sprzed
    wprowadzenia fallbacku — tylko `active_id` jest brany pod uwagę."""
    registry = _FakeRegistry()
    assert registry.chain == []
    router = LLMRouter(registry)

    chunks = [c async for c in router.generate_stream([LLMMessage(role="user", content="hi")])]

    assert chunks == ["A"]


@pytest.mark.anyio
async def test_llm_router_active_provider_is_always_priority_zero_even_absent_from_chain():
    """Regresja: `active_id` musi być próbowany PIERWSZY, niezależnie od tego, czy
    użytkownik w ogóle wpisał go do łańcucha fallbacku. Wcześniejsza wersja ignorowała
    aktywny preset w całości, gdy łańcuch był niepusty (a aktywnego w nim nie było) —
    preset oznaczony w UI jako "aktywny" nigdy nie był realnie wywoływany."""
    registry = _FakeRegistry()
    registry.active_id = "bk_a"
    registry.chain = ["bk_b"]  # świadomie BEZ "bk_a"
    router = LLMRouter(registry)

    chunks = [c async for c in router.generate_stream([LLMMessage(role="user", content="hi")])]

    assert chunks == ["A"]
    assert registry.providers["bk_b"].call_count == 0


@pytest.mark.anyio
async def test_llm_router_deduplicates_active_id_duplicated_in_chain():
    """Regresja: aktywny preset zduplikowany na liście fallbacku nie jest próbowany
    dwa razy w tej samej turze — filtrowany z pozostałej części łańcucha."""
    registry = _FakeRegistry()
    registry.active_id = "bk_a"
    registry.providers["bk_a"] = _FakeProvider("A", fail_before_yield=True)
    registry.chain = ["bk_a", "bk_b"]
    router = LLMRouter(registry)

    chunks = [c async for c in router.generate_stream([LLMMessage(role="user", content="hi")])]

    assert chunks == ["B"]
    assert registry.providers["bk_a"].call_count == 1


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
    """Regresja: `PUT /stt/providers/{id}` edytuje `options` aktywnej instancji
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
