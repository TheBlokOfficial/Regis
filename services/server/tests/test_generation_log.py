"""Telemetria wywołań LLM: zrzut, korelacja z turą, rotacja i API podglądu.

Sedno całego mechanizmu jest w pierwszym teście: dynamiczny system prompt i ulotny
`turn_context` **nie istnieją nigdzie poza momentem wywołania** — nie ma ich ani
w `data/sessions/*.json`, ani w żadnym stanie, który dałoby się odpytać po fakcie.
Jeśli zrzut ich nie zapamięta w tej jednej chwili, przepadają.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest
from fastapi.testclient import TestClient
from server.agent import AgentEngine
from server.agent.context_provider import ContextBuild
from server.agent.memory import MemoryManager
from server.agent.prompts import AgentDefaultPromptStore
from server.ai.llm.registry import BackendRegistry
from server.ai.llm.router import LLMAttempt
from server.network.gateway import create_gateway_app
from server.ports.llm import (
    BaseLLMProvider,
    GenerationUsage,
    LLMMessage,
    ReasoningChunk,
    ToolCallRequest,
    ToolDefinition,
    ToolResult,
)
from server.telemetry import GenerationLogStore, RecordingLLMProvider, TurnAttemptCollector
from server.telemetry.models import GenerationRecord, MessageSnapshot


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# ==========================================================================
# Atrapy
# ==========================================================================


class _PlainProvider(BaseLLMProvider):
    """Odpowiada tekstem i rozlicza generację — najprostszy realistyczny dostawca."""

    def __init__(self) -> None:
        self._model = "mock-plain"

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        del messages, tools, kwargs
        yield "Gotowe."
        yield GenerationUsage(prompt_tokens=100, completion_tokens=2, finish_reason="stop", model="mock-plain")


class _ToolThenAnswerProvider(BaseLLMProvider):
    """Pełna pętla ReAct: pierwsze wywołanie żąda narzędzia, drugie odpowiada."""

    def __init__(self) -> None:
        self._model = "mock-react"
        self.call_count = 0

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        del tools, kwargs
        self.call_count += 1
        if self.call_count == 1:
            yield ToolCallRequest(id="c1", name="probe", arguments={})
            yield GenerationUsage(prompt_tokens=50, completion_tokens=9, finish_reason="tool_calls")
        else:
            yield "Gotowe."
            yield GenerationUsage(prompt_tokens=80, completion_tokens=2, finish_reason="stop")


class _ReasoningProvider(BaseLLMProvider):
    """Model myśli, potem odpowiada — rozumowanie i tekst to dwa różne wyjścia."""

    def __init__(self) -> None:
        self._model = "mock-reasoning"

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        del messages, tools, kwargs
        yield ReasoningChunk(text="Zastanawiam się.")
        yield "Gotowe."
        yield GenerationUsage(prompt_tokens=10, completion_tokens=5, finish_reason="stop")


class _ExplodingProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self._model = "mock-boom"

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        del messages, tools, kwargs
        raise RuntimeError("Błąd API [https://api.example.com] HTTP 429: org_01ABC rate limit")
        yield ""  # pragma: no cover - nieosiągalne, wymusza async generator


class _WorldWithVolatileContext:
    """Silnik świata dostarczający oba rodzaje treści, które nie przeżywają tury."""

    SYSTEM_PROMPT = "# Tożsamość\nJesteś Regis."
    TURN_CONTEXT = "Stan urządzeń: lampa w salonie = ON. Data: 2026-08-25."

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        del sender_id

        async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            del name, arguments
            return ToolResult(content="wykonano")

        return ContextBuild(
            tool_definitions=[
                ToolDefinition(name="probe", description="d", parameters={"type": "object", "properties": {}})
            ],
            system_prompt=self.SYSTEM_PROMPT,
            turn_context=self.TURN_CONTEXT,
            dispatch=dispatch,
        )


class _BrokenWorld:
    """Silnik świata, który pada przy budowie kontekstu — tura nigdy nie dojdzie do LLM."""

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        del sender_id
        raise RuntimeError("Home Assistant nie odpowiada")


async def _engine_with_telemetry(
    tmp_dir: str, provider: BaseLLMProvider, world: Any = None
) -> tuple[AgentEngine, GenerationLogStore, TurnAttemptCollector]:
    store = GenerationLogStore(db_path=Path(tmp_dir) / "telemetry" / "generations.db")
    await store.start()
    collector = TurnAttemptCollector()
    recording = RecordingLLMProvider(provider, store, collector)

    kwargs: dict[str, Any] = {
        "llm_provider": recording,
        "memory_manager": MemoryManager(data_dir=Path(tmp_dir) / "sessions"),
    }
    if world is not None:
        kwargs["world"] = world
    engine = AgentEngine(**kwargs)
    recording.subscribe(engine.event_bus)
    return engine, store, collector


async def _drain(store: GenerationLogStore) -> None:
    """Zapis jest asynchroniczny z założenia — test musi domknąć writera, zanim czyta."""
    await store.stop()


# ==========================================================================
# Zrzut kontekstu
# ==========================================================================


@pytest.mark.anyio
async def test_snapshot_preserves_prompt_parts_that_leave_no_other_trace() -> None:
    """Ani system prompt, ani `turn_context` nie trafiają do pamięci sesji — a mimo to
    muszą być odtwarzalne z telemetrii co do znaku."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, store, _ = await _engine_with_telemetry(tmp_dir, _PlainProvider(), _WorldWithVolatileContext())

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="włącz światło")]
        await _drain(store)

        listing = await store.list_entries()
        assert len(listing.entries) == 1
        detail = await store.get_entry(listing.entries[0].id)
        assert detail is not None

        contents = [m.content for m in detail.messages]
        assert _WorldWithVolatileContext.TURN_CONTEXT in contents
        assert any(c.startswith(_WorldWithVolatileContext.SYSTEM_PROMPT) for c in contents)

        # Dowód, że to naprawdę jedyne miejsce: w historii sesji nie ma po nich śladu.
        history_contents = [m.content for m in engine.memory_manager.get_history(session_id="s1")]
        assert _WorldWithVolatileContext.TURN_CONTEXT not in history_contents

        # Fakty tury stoją TUŻ PRZED pytaniem użytkownika (kontrakt `ContextBuilder`).
        assert contents.index(_WorldWithVolatileContext.TURN_CONTEXT) == len(contents) - 2
        assert contents[-1] == "włącz światło"


@pytest.mark.anyio
async def test_react_loop_produces_one_record_per_llm_call_with_growing_context() -> None:
    """Sedno wyboru „request-first": w jednej turze zapada N wywołań, a każde widziało
    inny kontekst. Zapis per tura zlepiłby je w jeden i zgubił właśnie tę różnicę."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, store, _ = await _engine_with_telemetry(
            tmp_dir, _ToolThenAnswerProvider(), _WorldWithVolatileContext()
        )

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="sprawdź")]
        await _drain(store)

        entries = sorted((await store.list_entries()).entries, key=lambda e: e.call_index)
        assert [e.call_index for e in entries] == [0, 1]
        assert len({e.turn_id for e in entries}) == 1
        assert [e.finish_reason for e in entries] == ["tool_calls", "stop"]
        assert entries[0].tool_calls == 1 and entries[1].tool_calls == 0

        first = await store.get_entry(entries[0].id)
        second = await store.get_entry(entries[1].id)
        assert first is not None and second is not None
        # Druga runda dostała dodatkowo wiadomość assistant z wywołaniem i wynik narzędzia.
        assert len(second.messages) > len(first.messages)
        assert [m.role for m in second.messages][-2:] == ["assistant", "tool"]


@pytest.mark.anyio
async def test_record_pairs_the_context_with_what_the_model_generated() -> None:
    """Wejście i wyjście w jednym rekordzie — powiązanie nie potrzebuje klucza obcego,
    bo wpis JEST jednym wywołaniem dostawcy."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, store, _ = await _engine_with_telemetry(tmp_dir, _ReasoningProvider())

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]
        await _drain(store)

        detail = await store.get_entry((await store.list_entries()).entries[0].id)
        assert detail is not None
        assert detail.answer == "Gotowe."
        # Rozumowanie nie istnieje NIGDZIE indziej: nie wchodzi do pamięci sesji ani
        # nie wraca do modelu, więc telemetria jest jedynym jego śladem.
        assert detail.reasoning == "Zastanawiam się."
        assert engine.memory_manager.get_history(session_id="s1")[-1].content == "Gotowe."


@pytest.mark.anyio
async def test_tool_round_records_requested_calls_and_empty_answer() -> None:
    """Runda zakończona wywołaniem narzędzia nie ma tekstu odpowiedzi — i to jest
    poprawny stan, nie brak danych."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, store, _ = await _engine_with_telemetry(
            tmp_dir, _ToolThenAnswerProvider(), _WorldWithVolatileContext()
        )

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="sprawdź")]
        await _drain(store)

        entries = sorted((await store.list_entries()).entries, key=lambda e: e.call_index)
        first = await store.get_entry(entries[0].id)
        second = await store.get_entry(entries[1].id)
        assert first is not None and second is not None

        assert first.answer == ""
        assert [c["name"] for c in first.response_tool_calls] == ["probe"]
        assert second.answer == "Gotowe."
        assert second.response_tool_calls == []


@pytest.mark.anyio
async def test_real_usage_is_marked_as_not_estimated() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, store, _ = await _engine_with_telemetry(tmp_dir, _PlainProvider())

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]
        await _drain(store)

        entry = (await store.list_entries()).entries[0]
        assert entry.prompt_tokens == 100
        assert entry.completion_tokens == 2
        assert entry.estimated is False
        assert entry.status == "ok"


@pytest.mark.anyio
async def test_error_record_keeps_raw_provider_message() -> None:
    """Czat pokazuje `USER_FACING_ERROR`, panel diagnostyczny — surową treść.

    Rozdział jest świadomy: to ten sam błąd, który w UI musi być zredagowany (potrafi
    nieść ID organizacji dostawcy), a w narzędziu do debugowania jest bezużyteczny
    zredagowany. Patrz `docs/manifest.md`."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, store, _ = await _engine_with_telemetry(tmp_dir, _ExplodingProvider())

        with pytest.raises(RuntimeError):
            _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]
        await _drain(store)

        entries = (await store.list_entries()).entries
        assert len(entries) == 1
        assert entries[0].status == "error"

        detail = await store.get_entry(entries[0].id)
        assert detail is not None and detail.error is not None
        assert "org_01ABC" in detail.error

        # Użytkownik w historii sesji widzi wyłącznie wersję sanityzowaną.
        last = engine.memory_manager.get_history(session_id="s1")[-1]
        assert "org_01ABC" not in last.content


@pytest.mark.anyio
async def test_turn_that_never_reached_the_model_is_still_recorded() -> None:
    """Awaria budowy kontekstu nie zostawia żadnego żądania do zalogowania — bez wpisu
    `no_generation` najciekawsze awarie byłyby w panelu niewidoczne."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, store, _ = await _engine_with_telemetry(tmp_dir, _PlainProvider(), _BrokenWorld())

        with pytest.raises(RuntimeError):
            _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]
        await _drain(store)

        entries = (await store.list_entries()).entries
        assert len(entries) == 1
        assert entries[0].status == "no_generation"
        assert entries[0].session_id == "s1"
        assert entries[0].turn_id is not None


@pytest.mark.anyio
async def test_successful_turn_does_not_add_a_no_generation_record() -> None:
    """Domykanie tur bez wywołania nie może dokładać duplikatu do tur udanych."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, store, _ = await _engine_with_telemetry(tmp_dir, _PlainProvider())

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]
        await _drain(store)

        entries = (await store.list_entries()).entries
        assert [e.status for e in entries] == ["ok"]


# ==========================================================================
# Łańcuch fallbacku
# ==========================================================================


@pytest.mark.anyio
async def test_record_carries_every_fallback_attempt() -> None:
    """Dekorator stoi NAD routerem, więc sam nie zobaczyłby, że pierwszy kandydat
    odpadł. Kolektor prób jest jedynym kanałem, którym ta wiedza dociera do wpisu."""

    class _ReportingProvider(BaseLLMProvider):
        """Udaje router: najpierw zgłasza nieudanego kandydata, potem odpowiada."""

        def __init__(self, collector: TurnAttemptCollector) -> None:
            self._model = "mock-chain"
            self._collector = collector

        async def generate_stream(
            self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
        ) -> AsyncIterator[Any]:
            del messages, tools, kwargs
            self._collector.record(
                LLMAttempt(
                    instance_id="bk_groq",
                    instance_name="Groq",
                    provider_type="GROQ",
                    model="llama-3.3-70b",
                    position=0,
                    outcome="error",
                    error="HTTP 429",
                )
            )
            self._collector.record(
                LLMAttempt(
                    instance_id="bk_ollama",
                    instance_name="Ollama lokalnie",
                    provider_type="OLLAMA",
                    model="llama3",
                    position=1,
                    outcome="ok",
                )
            )
            yield "Gotowe."

    with tempfile.TemporaryDirectory() as tmp_dir:
        store = GenerationLogStore(db_path=Path(tmp_dir) / "generations.db")
        await store.start()
        collector = TurnAttemptCollector()
        recording = RecordingLLMProvider(_ReportingProvider(collector), store, collector)
        engine = AgentEngine(
            llm_provider=recording, memory_manager=MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        )
        recording.subscribe(engine.event_bus)

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]
        await _drain(store)

        entries = (await store.list_entries()).entries
        assert len(entries) == 1
        entry = entries[0]
        assert entry.attempt_count == 2
        # Wpis opisany jest kandydatem, który faktycznie obsłużył turę — nie pierwszym.
        assert entry.instance_name == "Ollama lokalnie"
        assert entry.provider_type == "OLLAMA"

        detail = await store.get_entry(entry.id)
        assert detail is not None
        assert [a.outcome for a in detail.attempts] == ["error", "ok"]
        assert detail.attempts[0].error == "HTTP 429"


# ==========================================================================
# Magazyn
# ==========================================================================


def _record(index: int) -> GenerationRecord:
    return GenerationRecord(created_at=float(index), session_id="s1", turn_id=f"turn_{index}", status="ok")


@pytest.mark.anyio
async def test_rotation_keeps_only_the_newest_records() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = GenerationLogStore(db_path=Path(tmp_dir) / "generations.db", retention_records=10)
        await store.start()

        # Ponad próg rotacji (`_PRUNE_EVERY`), żeby leniwe czyszczenie w ogóle wystartowało.
        for i in range(120):
            store.submit(_record(i))
        await _drain(store)

        entries = (await store.list_entries(limit=200)).entries
        assert len(entries) == 10
        assert entries[0].turn_id == "turn_119"


@pytest.mark.anyio
async def test_oversized_snapshot_is_truncated_but_keeps_its_structure() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = GenerationLogStore(db_path=Path(tmp_dir) / "generations.db", max_record_bytes=2048)
        await store.start()

        store.submit(
            _record(1).model_copy(
                update={
                    "messages": [
                        MessageSnapshot(role="system", content="x" * 50_000),
                        MessageSnapshot(role="user", content="krótka wiadomość"),
                    ]
                }
            )
        )
        await _drain(store)

        entry = (await store.list_entries()).entries[0]
        assert entry.truncated is True
        assert entry.message_count == 2

        detail = await store.get_entry(entry.id)
        assert detail is not None
        assert len(detail.messages[0].content) < 50_000
        # Krótka wiadomość nie jest ruszana — ucinanie ma budżet per wiadomość.
        assert detail.messages[1].content == "krótka wiadomość"


@pytest.mark.anyio
async def test_existing_database_gains_new_columns_without_losing_records() -> None:
    """`CREATE TABLE IF NOT EXISTS` nie dotyka istniejącej tabeli, więc rozszerzenie
    rekordu o nowe pola musi domknąć addytywna migracja — inaczej baza użytkownika
    przestałaby przyjmować zapisy po aktualizacji."""
    import sqlite3

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "generations.db"

        # Baza w kształcie sprzed dołożenia sekcji odpowiedzi, z jednym starym wpisem.
        legacy = sqlite3.connect(db_path)
        legacy.executescript(
            """
            CREATE TABLE generations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at REAL NOT NULL, session_id TEXT, turn_id TEXT,
                call_index INTEGER NOT NULL DEFAULT 0, sender_id TEXT,
                model TEXT, provider_type TEXT, instance_id TEXT, instance_name TEXT,
                status TEXT NOT NULL, finish_reason TEXT, error TEXT,
                prompt_tokens INTEGER, completion_tokens INTEGER, cached_tokens INTEGER,
                estimated INTEGER NOT NULL DEFAULT 1,
                ttft_ms REAL, total_ms REAL, output_tps REAL,
                tool_calls INTEGER NOT NULL DEFAULT 0,
                message_count INTEGER NOT NULL DEFAULT 0,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                truncated INTEGER NOT NULL DEFAULT 0,
                messages_json TEXT NOT NULL, tools_json TEXT NOT NULL, attempts_json TEXT NOT NULL
            );
            INSERT INTO generations (created_at, status, messages_json, tools_json, attempts_json)
            VALUES (1.0, 'ok', '[]', '[]', '[]');
            """
        )
        legacy.commit()
        legacy.close()

        store = GenerationLogStore(db_path=db_path)
        await store.start()
        store.submit(_record(2).model_copy(update={"answer": "nowy wpis"}))
        await _drain(store)

        entries = (await store.list_entries()).entries
        assert len(entries) == 2, "Stary wpis musi przetrwać migrację"

        migrated = await store.get_entry(min(e.id for e in entries))
        assert migrated is not None
        assert migrated.answer == ""
        assert migrated.response_tool_calls == []

        fresh = await store.get_entry(max(e.id for e in entries))
        assert fresh is not None and fresh.answer == "nowy wpis"


@pytest.mark.anyio
async def test_listing_paginates_with_cursor_and_filters_by_session() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = GenerationLogStore(db_path=Path(tmp_dir) / "generations.db")
        await store.start()

        for i in range(5):
            store.submit(_record(i))
        store.submit(_record(99).model_copy(update={"session_id": "inna"}))
        await _drain(store)

        first_page = await store.list_entries(limit=2)
        assert len(first_page.entries) == 2
        assert first_page.next_before_id == first_page.entries[-1].id

        second_page = await store.list_entries(limit=2, before_id=first_page.next_before_id)
        assert {e.id for e in second_page.entries}.isdisjoint({e.id for e in first_page.entries})

        assert len((await store.list_entries(session_id="inna")).entries) == 1
        assert len((await store.list_entries(turn_id="turn_3")).entries) == 1


# ==========================================================================
# REST
# ==========================================================================


@pytest.fixture
def telemetry_client():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        store = GenerationLogStore(db_path=tmp_path / "generations.db")
        prompt_store = AgentDefaultPromptStore(data_dir=tmp_path)
        app = create_gateway_app(
            agent_engine=AgentEngine(
                llm_provider=_PlainProvider(),
                memory_manager=MemoryManager(data_dir=tmp_path / "sessions"),
                prompt_store=prompt_store,
            ),
            backend_registry=BackendRegistry(data_dir=tmp_path / "backends"),
            prompt_store=prompt_store,
            generation_log=store,
        )
        with TestClient(app) as client:
            yield client, store


def test_telemetry_endpoints_list_detail_and_clear(telemetry_client) -> None:
    client, store = telemetry_client

    async def seed() -> None:
        await store.start()
        store.submit(
            _record(1).model_copy(
                update={"messages": [MessageSnapshot(role="user", content="cześć")], "model": "mock"}
            )
        )
        await store.stop()

    import anyio

    anyio.run(seed)

    listing = client.get("/api/v1/telemetry/generations")
    assert listing.status_code == 200
    entries = listing.json()["entries"]
    assert len(entries) == 1
    assert entries[0]["model"] == "mock"
    # Wiersz listy celowo nie niesie zrzutu kontekstu.
    assert "messages" not in entries[0]

    detail = client.get(f"/api/v1/telemetry/generations/{entries[0]['id']}")
    assert detail.status_code == 200
    assert detail.json()["messages"][0]["content"] == "cześć"

    assert client.get("/api/v1/telemetry/generations/999999").status_code == 404

    cleared = client.delete("/api/v1/telemetry/generations")
    assert cleared.status_code == 200 and cleared.json()["deleted"] == 1
    assert client.get("/api/v1/telemetry/generations").json()["entries"] == []
