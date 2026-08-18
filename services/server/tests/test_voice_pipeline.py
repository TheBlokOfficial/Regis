"""Testy jednostkowe pipeline'u głosowego: automat `VoiceSession` (bez prawdziwego
WebSocket) i mechanizm `ToolResult.redirect_sender_id` w kernelu (bez `server.voice`,
bez `server.world` — czysto na fałszywym `WorldInterface`, żeby zweryfikować, że
kernel obsługuje przekierowanie mechanicznie, niezależnie od tego, kto je ustawia).
"""

import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest

from server.agent import AgentEngine
from server.agent.backend import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition, ToolResult
from server.agent.context_provider import ContextBuild
from server.agent.memory import MemoryManager
from server.events import ServerEventType
from server.voice.protocol import ServerMessageType
from server.voice.session import VoiceSession
from server.voice.stt import BaseSTTProvider
from server.voice.tts import BaseTTSProvider
from server.voice.wakeword import ThresholdEnergyWakeWordDetector, WakeWordDetector

# --------------------------------------------------------------------------
# VoiceSession — automat stanu, bez prawdziwego WebSocket/kernela
# --------------------------------------------------------------------------


class FakeLink:
    def __init__(self) -> None:
        self.control_messages: list[ServerMessageType] = []
        self.audio_chunks: list[bytes] = []

    async def send_control(self, message_type: ServerMessageType) -> None:
        self.control_messages.append(message_type)

    async def send_audio(self, chunk: bytes) -> None:
        self.audio_chunks.append(chunk)


class AlwaysTriggerWakeWordDetector:
    """Wyzwala się na pierwszej ramce — deterministyczny detektor testowy."""

    def process(self, pcm_chunk: bytes) -> bool:
        del pcm_chunk
        return True

    def reset(self) -> None:
        pass


class NeverTriggerWakeWordDetector:
    def process(self, pcm_chunk: bytes) -> bool:
        del pcm_chunk
        return False

    def reset(self) -> None:
        pass


class FakeSTT(BaseSTTProvider):
    async def transcribe(self, pcm_audio: bytes) -> str:
        return f"transkrypcja({len(pcm_audio)} bajtów)"


class FakeTTS(BaseTTSProvider):
    async def synthesize(self, text: str) -> bytes:
        return f"audio:{text}".encode()


def _make_session(
    wakeword_detector: WakeWordDetector,
    on_transcript,
) -> tuple[VoiceSession, FakeLink]:
    link = FakeLink()
    session = VoiceSession(
        sender_id="snd_test",
        link=link,
        wakeword_detector=wakeword_detector,
        stt_provider=FakeSTT(),
        tts_provider=FakeTTS(),
        on_transcript=on_transcript,
    )
    return session, link


@pytest.mark.anyio
async def test_wake_word_transitions_to_recording_and_sends_wake_detected():
    session, link = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None)

    await session.handle_audio_frame(b"\x00\x01")

    assert session.state.name == "RECORDING_UTTERANCE"
    assert link.control_messages == [ServerMessageType.WAKE_DETECTED]


@pytest.mark.anyio
async def test_audio_frames_ignored_before_wake_word():
    session, link = _make_session(NeverTriggerWakeWordDetector(), on_transcript=lambda t: None)

    await session.handle_audio_frame(b"\x00\x01")

    assert session.state.name == "LISTENING_WAKEWORD"
    assert link.control_messages == []


@pytest.mark.anyio
async def test_utterance_end_transcribes_and_calls_on_transcript_then_stop_tone():
    seen_transcripts: list[str] = []
    session, link = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=seen_transcripts.append)

    await session.handle_audio_frame(b"\x00\x01")  # wake-word
    await session.handle_audio_frame(b"\x02\x03\x04\x05")  # nagrywana wypowiedź
    await session.handle_utterance_end()

    assert link.control_messages == [ServerMessageType.WAKE_DETECTED, ServerMessageType.PLAY_STOP_TONE]
    assert seen_transcripts == ["transkrypcja(4 bajtów)"]
    assert session.state.name == "PROCESSING"


@pytest.mark.anyio
async def test_utterance_end_outside_recording_is_ignored():
    session, link = _make_session(NeverTriggerWakeWordDetector(), on_transcript=lambda t: None)

    await session.handle_utterance_end()

    assert session.state.name == "LISTENING_WAKEWORD"
    assert link.control_messages == []


@pytest.mark.anyio
async def test_speak_sends_tts_frames_and_transitions_to_speaking():
    session, link = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None)

    await session.speak("Cześć!")

    assert session.state.name == "SPEAKING"
    assert link.control_messages == [ServerMessageType.TTS_START, ServerMessageType.TTS_END]
    assert link.audio_chunks == [b"audio:Cze\xc5\x9b\xc4\x87!"]


@pytest.mark.anyio
async def test_playback_done_returns_to_listening_and_resets_detector():
    class CountingResetDetector(AlwaysTriggerWakeWordDetector):
        def __init__(self) -> None:
            self.reset_count = 0

        def reset(self) -> None:
            self.reset_count += 1

    detector = CountingResetDetector()
    session, _ = _make_session(detector, on_transcript=lambda t: None)
    await session.speak("Test")

    await session.handle_playback_done()

    assert session.state.name == "LISTENING_WAKEWORD"
    assert detector.reset_count == 1


@pytest.mark.anyio
async def test_audio_frames_ignored_while_speaking():
    session, link = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None)
    await session.speak("Test")

    await session.handle_audio_frame(b"\x00\x01")

    assert session.state.name == "SPEAKING"  # nie przełączyło się na RECORDING_UTTERANCE


@pytest.mark.anyio
async def test_reset_to_listening_recovers_from_stuck_processing():
    """Bez tego, błąd/anulowanie tury (server.voice/gateway.py, _on_error_or_cancelled)
    zostawiałoby sesję uwięzioną w PROCESSING na zawsze."""
    session, _ = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None)
    await session.handle_audio_frame(b"\x00\x01")
    await session.handle_audio_frame(b"\x02\x03")
    await session.handle_utterance_end()
    assert session.state.name == "PROCESSING"

    session.reset_to_listening()

    assert session.state.name == "LISTENING_WAKEWORD"


def test_threshold_energy_detector_triggers_after_consecutive_loud_frames():
    detector = ThresholdEnergyWakeWordDetector(loud_frames_required=2, amplitude_threshold=1000)
    loud_frame = (30000).to_bytes(2, byteorder="little", signed=True)
    quiet_frame = (10).to_bytes(2, byteorder="little", signed=True)

    assert detector.process(loud_frame) is False
    assert detector.process(loud_frame) is True  # druga kolejna głośna ramka -> wykrycie
    assert detector.process(quiet_frame) is False  # licznik zresetowany po wykryciu i po cichej ramce


# --------------------------------------------------------------------------
# Kernel — ToolResult.redirect_sender_id zmienia tag dostawy zdarzeń
# --------------------------------------------------------------------------


class _RedirectWorld:
    """Fałszywy WorldInterface z jednym narzędziem przekierowującym dostawę."""

    async def build(self, sender_id: str | None = None, voice_mode: bool = False) -> ContextBuild:
        del sender_id, voice_mode

        async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            del arguments
            if name == "redirect_tool":
                return ToolResult(content="Przełączono.", redirect_sender_id="target_x")
            return ToolResult(is_error=True, content="nieznane narzędzie")

        return ContextBuild(
            tool_definitions=[
                ToolDefinition(name="redirect_tool", description="d", parameters={"type": "object", "properties": {}})
            ],
            dynamic_context="",
            dispatch=dispatch,
        )


class _RedirectMockProvider(BaseLLMProvider):
    """Pierwsza tura woła redirect_tool, druga zwraca finalny tekst (po przekierowaniu)."""

    def __init__(self) -> None:
        self._model = "mock-redirect"
        self._call_count = 0

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        self._call_count += 1
        if self._call_count == 1:
            yield ToolCallRequest(id="c1", name="redirect_tool", arguments={})
        else:
            yield "Hello after redirect"

    async def check_health(self) -> bool:
        return True


@pytest.mark.anyio
async def test_redirect_sender_id_changes_chunk_delivery_tag():
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=_RedirectMockProvider(), memory_manager=memory_manager, world=_RedirectWorld())

        chunk_events: list[tuple[str, str]] = []
        done_session_ids: list[str] = []

        async def on_chunk(event: Any) -> None:
            chunk_events.append((event.payload["session_id"], event.payload["chunk"]))

        async def on_done(event: Any) -> None:
            done_session_ids.append(event.payload["session_id"])

        engine.event_bus.subscribe(ServerEventType.CHAT_CHUNK, on_chunk)
        engine.event_bus.subscribe(ServerEventType.CHAT_DONE, on_done)

        # interact_stream() jest subskrybowany wyłącznie po oryginalnym "orig" — musi
        # się poprawnie zakończyć mimo przekierowania (nie zawiesić się w oczekiwaniu na done).
        stream_events = [event async for event in engine.interact_stream(session_id="orig", prompt="cześć")]

        assert all(sid == "target_x" for sid, _ in chunk_events)
        assert "".join(chunk for _, chunk in chunk_events) == "Hello after redirect"
        # CHAT_DONE dostarczony pod obydwoma tagami: oryginalnym (dla plumbingu kernela)
        # i przekierowanym (dla niezależnego, ciągłego słuchacza pod nowym sender_id).
        assert set(done_session_ids) == {"orig", "target_x"}
        assert stream_events[-1].type != "error"

        # Historia rozmowy nadal zapisana pod oryginalnym session_id — przekierowanie
        # zmienia tylko dostawę, nigdy właściciela konwersacji.
        history = memory_manager.get_history(session_id="orig")
        assert history[-1].content == "Hello after redirect"


@pytest.mark.anyio
async def test_redirect_sender_id_not_used_when_tool_does_not_redirect():
    class NoRedirectWorld:
        async def build(self, sender_id: str | None = None, voice_mode: bool = False) -> ContextBuild:
            del sender_id, voice_mode

            async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
                del name, arguments
                return ToolResult(content="ok")

            return ContextBuild(
                tool_definitions=[ToolDefinition(name="redirect_tool", description="d", parameters={"type": "object", "properties": {}})],
                dynamic_context="",
                dispatch=dispatch,
            )

    with tempfile.TemporaryDirectory() as tmp_dir:
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=_RedirectMockProvider(), memory_manager=memory_manager, world=NoRedirectWorld())

        done_events: list[Any] = []

        async def on_done(event: Any) -> None:
            done_events.append(event)

        engine.event_bus.subscribe(ServerEventType.CHAT_DONE, on_done)

        _ = [event async for event in engine.interact_stream(session_id="orig", prompt="cześć")]

        # Bez przekierowania: dokładnie jedna publikacja CHAT_DONE (brak zduplikowanego dual-cast).
        assert len([e for e in done_events if e.payload["session_id"] == "orig"]) == 1
