"""Rozumowanie modelu (chain of thought) jest osobnym typem zdarzenia, nie tekstem
odpowiedzi ze znacznikiem `<think>` w środku.

Dopóki obie rzeczy płynęły jednym strumieniem stringów, jeden korzeń dawał trzy
osobne objawy: satelita czytała rozumowanie na głos, chain of thought lądował w
pamięci sesji i wracał do modelu w każdej kolejnej turze, a Web UI odzyskiwało
podział parsując strumień znak po znaku. Te testy pilnują wszystkich trzech granic.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest

from server.agent import AgentEngine
from server.agent.context_provider import ContextBuild
from server.agent.llm import (
    BaseLLMProvider,
    LLMMessage,
    ReasoningChunk,
    ToolCallRequest,
    ToolDefinition,
    ToolResult,
)
from server.agent.memory import MemoryManager
from server.events import ServerEventType


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _ReasoningThenTextProvider(BaseLLMProvider):
    """Model myśli, potem odpowiada — bez żadnych narzędzi."""

    def __init__(self) -> None:
        self._model = "mock-reasoning"

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        del messages, tools, kwargs
        yield ReasoningChunk(text="Użytkownik pyta o ")
        yield ReasoningChunk(text="pogodę.")
        yield "Jest słonecznie."

    async def check_health(self) -> bool:
        return True


class _ToolThenAnswerProvider(BaseLLMProvider):
    """Pełny przebieg ReAct: myślenie -> narzędzie -> myślenie -> odpowiedź.

    Zapamiętuje wiadomości z DRUGIEGO wywołania, żeby dało się sprawdzić, co dokładnie
    kernel odesłał modelowi w kolejnej rundzie pętli."""

    def __init__(self) -> None:
        self._model = "mock-react"
        self.call_count = 0
        self.second_call_messages: list[LLMMessage] = []

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        del tools, kwargs
        self.call_count += 1
        if self.call_count == 1:
            yield ReasoningChunk(text="Trzeba sprawdzić stan.")
            yield ToolCallRequest(id="c1", name="probe", arguments={})
        else:
            self.second_call_messages = list(messages)
            yield ReasoningChunk(text="Mam wynik.")
            yield "Gotowe."

    async def check_health(self) -> bool:
        return True


class _ProbeWorld:
    async def build(self, sender_id: str | None = None) -> ContextBuild:
        del sender_id

        async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            del name, arguments
            return ToolResult(content="stan: ok")

        return ContextBuild(
            tool_definitions=[
                ToolDefinition(name="probe", description="d", parameters={"type": "object", "properties": {}})
            ],
            system_prompt="",
            turn_context=None,
            dispatch=dispatch,
        )


def _engine(provider: BaseLLMProvider, tmp_dir: str, world: Any = None) -> tuple[AgentEngine, MemoryManager]:
    memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
    kwargs: dict[str, Any] = {"llm_provider": provider, "memory_manager": memory_manager}
    if world is not None:
        kwargs["world"] = world
    return AgentEngine(**kwargs), memory_manager


@pytest.mark.anyio
async def test_reasoning_never_reaches_persisted_content() -> None:
    """Sedno całej zmiany: `content` wiadomości assistant to WYŁĄCZNIE odpowiedź.

    `content` wraca do modelu jako historia w każdej kolejnej turze i jest czytany na
    głos przez TTS — rozumowanie w tym polu kosztowało tokeny i psuło mowę."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, memory = _engine(_ReasoningThenTextProvider(), tmp_dir)

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="jaka pogoda?")]

        last = memory.get_history(session_id="s1")[-1]
        assert last.content == "Jest słonecznie."
        assert "Użytkownik pyta" not in last.content
        assert "<think>" not in last.content


@pytest.mark.anyio
async def test_reasoning_is_persisted_in_metadata_as_one_run() -> None:
    """Kolejne fragmenty rozumowania sklejają się w JEDEN przebieg — dokładnie tak,
    jak wyglądał pojedynczy blok `<think>…</think>` przed tą zmianą."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, memory = _engine(_ReasoningThenTextProvider(), tmp_dir)

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="jaka pogoda?")]

        runs = memory.get_history(session_id="s1")[-1].metadata["reasoning"]
        assert len(runs) == 1
        assert runs[0]["content"] == "Użytkownik pyta o pogodę."
        # Rozumowanie poprzedziło pierwszy znak odpowiedzi, więc kotwiczy się na zerze.
        assert runs[0]["text_offset"] == 0


@pytest.mark.anyio
async def test_chunk_events_carry_kind() -> None:
    """Odbiorca rozróżnia rodzaj tokena po polu `kind`, nie po treści."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, _ = _engine(_ReasoningThenTextProvider(), tmp_dir)

        seen: list[tuple[str, str]] = []

        async def on_chunk(event: Any) -> None:
            seen.append((event.payload["kind"], event.payload["chunk"]))

        engine.event_bus.subscribe(ServerEventType.CHAT_CHUNK, on_chunk)

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="jaka pogoda?")]

        assert seen == [
            ("reasoning", "Użytkownik pyta o "),
            ("reasoning", "pogodę."),
            ("answer", "Jest słonecznie."),
        ]


@pytest.mark.anyio
async def test_reasoning_is_not_sent_back_to_model_in_react_loop() -> None:
    """Wiadomość `assistant` odsyłana modelowi w kolejnej rundzie pętli ReAct niesie
    sam tekst odpowiedzi (tu: pusty) — nigdy rozumowania z poprzedniej rundy."""
    provider = _ToolThenAnswerProvider()
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, _ = _engine(provider, tmp_dir, world=_ProbeWorld())

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="sprawdź")]

        assistant_messages = [m for m in provider.second_call_messages if m.role == "assistant"]
        assert assistant_messages, "Druga runda powinna dostać wiadomość assistant z wywołaniem narzędzia."
        assert all("Trzeba sprawdzić stan." not in m.content for m in assistant_messages)


@pytest.mark.anyio
async def test_seq_orders_reasoning_against_tool_steps_at_the_same_offset() -> None:
    """Cała sekwencja myślenie -> narzędzie -> myślenie dzieje się przy offsecie 0,
    dopóki model nie napisze pierwszego znaku odpowiedzi — sam offset by ich nie
    rozróżnił, więc kolejność niesie `seq`."""
    provider = _ToolThenAnswerProvider()
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, memory = _engine(provider, tmp_dir, world=_ProbeWorld())

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="sprawdź")]

        metadata = memory.get_history(session_id="s1")[-1].metadata
        runs = metadata["reasoning"]
        steps = metadata["steps"]

        assert [r["content"] for r in runs] == ["Trzeba sprawdzić stan.", "Mam wynik."]
        # Pierwsze myślenie przed wywołaniem narzędzia, drugie po jego wyniku.
        assert runs[0]["seq"] < steps[0]["seq"]
        assert runs[1]["seq"] > steps[-1]["seq"]
        # Wszystko przy tym samym offsecie — dowód, że offset sam w sobie nie wystarcza.
        assert {r["text_offset"] for r in runs} == {0}
        assert {s["text_offset"] for s in steps} == {0}


@pytest.mark.anyio
async def test_turn_without_reasoning_has_no_reasoning_metadata() -> None:
    """Brak rozumowania = brak klucza, nie pusta lista.

    Front rozstrzyga po obecności klucza, czy użyć ścieżki legacy (`<think>` wprost
    w treści starych sesji), więc pusta lista udawałaby "nowy format, bez myślenia"."""

    class _PlainProvider(BaseLLMProvider):
        def __init__(self) -> None:
            self._model = "mock-plain"

        async def generate_stream(
            self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
        ) -> AsyncIterator[Any]:
            del messages, tools, kwargs
            yield "Bez myślenia."

        async def check_health(self) -> bool:
            return True

    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, memory = _engine(_PlainProvider(), tmp_dir)

        _ = [e async for e in engine.interact_stream(session_id="s1", prompt="hej")]

        # `MemoryManager` normalizuje brak metadanych do pustego dicta.
        assert memory.get_history(session_id="s1")[-1].metadata == {}
