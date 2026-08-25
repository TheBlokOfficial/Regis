"""`GenerationUsage` jest zdarzeniem strumienia, więc musi przejść tę samą bramkę
co `ReasoningChunk`: nie wolno mu wyciec do treści odpowiedzi.

Ryzyko jest realne i strukturalne, nie hipotetyczne — `TurnRunner._stream_one_round`
rozpoznaje po `isinstance` tylko to, co zna, a **wszystko pozostałe traktuje jak
tekst** (`turn_text += event`). Nowy typ zdarzenia bez jawnej gałęzi w tej pętli
wylądowałby więc w buforze odpowiedzi, stamtąd w pamięci sesji, a stamtąd z powrotem
w kontekście modelu i w mowie TTS. Ten sam korzeń, który opisuje `test_reasoning_split.py`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest
from server.agent import AgentEngine
from server.agent.memory import MemoryManager
from server.ai.llm.token_budget import TokenBudgetTracker
from server.ports.llm import (
    BaseLLMProvider,
    GenerationUsage,
    LLMMessage,
    ToolDefinition,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _UsageReportingProvider(BaseLLMProvider):
    """Odpowiada tekstem, a na koniec rozlicza generację — jak realny dostawca."""

    def __init__(self) -> None:
        self._model = "mock-usage"

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        del messages, tools, kwargs
        yield "Gotowe."
        yield GenerationUsage(
            prompt_tokens=120, completion_tokens=4, cached_tokens=64, finish_reason="stop", model="mock-usage"
        )


def _engine(provider: BaseLLMProvider, tmp_dir: str) -> tuple[AgentEngine, MemoryManager]:
    memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
    return AgentEngine(llm_provider=provider, memory_manager=memory_manager), memory_manager


@pytest.mark.anyio
async def test_usage_never_reaches_persisted_content_or_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, memory = _engine(_UsageReportingProvider(), tmp_dir)

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]

        last = memory.get_history(session_id="s1")[-1]
        assert last.content == "Gotowe."
        assert last.metadata == {}


@pytest.mark.anyio
async def test_usage_does_not_emit_a_chat_chunk() -> None:
    """Rozliczenie nie jest ani odpowiedzią, ani rozumowaniem — nie ma go na `EventBus`,
    więc żaden odbiorca (SSE, satelita) nie musi się bronić przed jego wyświetleniem."""
    from server.events import ServerEventType

    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, _ = _engine(_UsageReportingProvider(), tmp_dir)

        seen: list[str] = []

        async def on_chunk(event: Any) -> None:
            seen.append(event.payload["chunk"])

        engine.event_bus.subscribe(ServerEventType.CHAT_CHUNK, on_chunk)

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]

        assert seen == ["Gotowe."]


@pytest.mark.anyio
async def test_generate_collapses_stream_without_usage_leaking() -> None:
    """Niestrumieniowe `generate()` skleja wyłącznie `str` — rozliczenie odpada samo."""
    response = await _UsageReportingProvider().generate([LLMMessage(role="user", content="hej")])
    assert response.content == "Gotowe."


@pytest.mark.anyio
async def test_router_records_real_tokens_when_provider_reports_them() -> None:
    """Router odnotowuje w budżecie TPM realne zużycie, a nie estymatę `len/4`.

    Krótki prompt (~1 token estymaty) i deklarowane 124 tokeny to różnica dwóch rzędów
    wielkości — dokładnie ten rozjazd, przez który bramkowanie TPM potrafiło przepuścić
    turę, którą dostawca odrzucał potem przez 429."""
    from server.ai.llm.models import BackendFileContent, BackendInstanceConfig, ProviderType
    from server.ai.llm.router import LLMRouter

    provider = _UsageReportingProvider()

    class _StubRegistry:
        async def load_all_instances(self) -> dict[str, BackendInstanceConfig]:
            return {
                "only": BackendInstanceConfig(
                    id="only",
                    **BackendFileContent(type=ProviderType.OLLAMA, name="Stub", options={}).model_dump(),
                )
            }

        async def get_active_backend_id(self) -> str:
            return "only"

        async def get_fallback_chain(self) -> list[str]:
            return []

        def create_provider_instance(self, instance: BackendInstanceConfig) -> BaseLLMProvider:
            del instance
            return provider

    tracker = TokenBudgetTracker()
    router = LLMRouter(_StubRegistry(), tracker=tracker)  # type: ignore[arg-type]

    async for _ in router.generate_stream([LLMMessage(role="user", content="hej")]):
        pass

    assert tracker.used_tokens("only") == 124
