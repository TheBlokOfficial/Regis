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
from server.agent.context_provider import ContextBuild
from server.agent.llm import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition, ToolResult
from server.agent.memory import MemoryManager
from server.events import ServerEventType
from server.voice.session import VoiceSession
from server.voice.stt import BaseSTTProvider
from server.voice.tts import BaseTTSProvider
from server.voice.wakeword import ThresholdEnergyWakeWordDetector, WakeWordDetector
from shared import ServerMessageType

# --------------------------------------------------------------------------
# VoiceSession — automat stanu, bez prawdziwego WebSocket/kernela
# --------------------------------------------------------------------------


class FakeLink:
    def __init__(self) -> None:
        self.control_messages: list[ServerMessageType] = []
        self.audio_chunks: list[bytes] = []
        self.errors: list[str] = []

    async def send_control(self, message_type: ServerMessageType) -> None:
        self.control_messages.append(message_type)

    async def send_audio(self, chunk: bytes) -> None:
        self.audio_chunks.append(chunk)

    async def send_error(self, detail: str) -> None:
        self.errors.append(detail)


class AlwaysTriggerWakeWordDetector:
    """Wyzwala się na pierwszej ramce — deterministyczny detektor testowy."""

    def process(self, pcm_chunk: bytes) -> bool:
        del pcm_chunk
        return True

    def reset(self) -> None:
        pass

    @property
    def last_score(self) -> float | None:
        return 0.99


class NeverTriggerWakeWordDetector:
    def process(self, pcm_chunk: bytes) -> bool:
        del pcm_chunk
        return False

    def reset(self) -> None:
        pass

    @property
    def last_score(self) -> float | None:
        return None


class FakeSTT(BaseSTTProvider):
    async def transcribe(self, pcm_audio: bytes) -> str:
        return f"transkrypcja({len(pcm_audio)} bajtów)"


class FakeTTS(BaseTTSProvider):
    """Strumieniuje odpowiedź jako JEDEN fragment — wystarczy do testów, które nie
    weryfikują samego chunkowania (te mają dedykowane fejki niżej, patrz
    `test_speak_streams_multiple_chunks_as_they_arrive`)."""

    async def synthesize_stream(self, text: str):
        yield f"audio:{text}".encode()


async def _noop_publish_event(event_type, payload) -> None:
    del event_type, payload


def _make_session(
    wakeword_detector: WakeWordDetector,
    on_transcript,
    tts_provider: BaseTTSProvider | None = None,
) -> tuple[VoiceSession, FakeLink]:
    link = FakeLink()
    session = VoiceSession(
        sender_id="snd_test",
        link=link,
        wakeword_detector=wakeword_detector,
        stt_provider=FakeSTT(),
        tts_provider=tts_provider or FakeTTS(),
        on_transcript=on_transcript,
        publish_event=_noop_publish_event,
    )
    return session, link


@pytest.mark.anyio
async def test_wake_word_transitions_to_recording_and_sends_wake_detected():
    session, link = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None)

    await session.handle_audio_frame(b"\x00\x01")

    assert session.state.name == "RECORDING_UTTERANCE"
    assert link.control_messages == [ServerMessageType.WAKE_DETECTED]


@pytest.mark.anyio
async def test_wake_word_publishes_state_changed_and_detected_events_with_score():
    """Dashboard "Klienci" (Web UI) potrzebuje zarówno zmiany stanu, jak i score
    detekcji — zdarzenia muszą przyjść w tej kolejności (state dopiero PO score, bo
    ikonka ma zareagować na wykrycie, nie na wejście w RECORDING_UTTERANCE)."""
    from server.voice.events import VoiceEventType

    published: list[tuple[object, dict]] = []

    async def capture_publish_event(event_type, payload) -> None:
        published.append((event_type, payload))

    link = FakeLink()
    session = VoiceSession(
        sender_id="snd_test",
        link=link,
        wakeword_detector=AlwaysTriggerWakeWordDetector(),
        stt_provider=FakeSTT(),
        tts_provider=FakeTTS(),
        on_transcript=lambda t: None,
        publish_event=capture_publish_event,
    )

    await session.handle_audio_frame(b"\x00\x01")

    assert published[0] == (VoiceEventType.SATELLITE_WAKE_WORD_DETECTED, {"sender_id": "snd_test", "score": 0.99})
    assert published[1] == (
        VoiceEventType.SATELLITE_STATE_CHANGED,
        {"sender_id": "snd_test", "state": "RECORDING_UTTERANCE"},
    )


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
async def test_speak_streams_multiple_chunks_progressively():
    """Sedno streamingu: `tts_start` i pierwsza ramka lecą po PIERWSZYM fragmencie
    dostawcy, nie po zakończeniu całej syntezy — kolejne fragmenty dochodzą jako osobne
    ramki `send_audio`, nie jeden sklejony bufor."""

    class ChunkedTTS(BaseTTSProvider):
        def __init__(self) -> None:
            self.chunks_requested_before_first_send = 0

        async def synthesize_stream(self, text: str):
            del text
            yield b"pierwszy-"
            yield b"drugi-"
            yield b"trzeci"

    session, link = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None, tts_provider=ChunkedTTS())

    await session.speak("Cześć!")

    assert link.audio_chunks == [b"pierwszy-", b"drugi-", b"trzeci"]
    assert link.control_messages == [ServerMessageType.TTS_START, ServerMessageType.TTS_END]


@pytest.mark.anyio
async def test_speak_ends_stream_gracefully_when_provider_fails_mid_stream():
    """Wyjątek PO wysłaniu pierwszego fragmentu jest traktowany inaczej niż wyjątek przed
    nim: satelita ma już czym karmić głośnik, więc kończymy `tts_end` jak przy normalnym
    zakończeniu, zamiast zostawiać ją czekającą na ramki, których nie będzie."""

    class FlakyTTS(BaseTTSProvider):
        async def synthesize_stream(self, text: str):
            del text
            yield b"poczatek-"
            raise RuntimeError("połączenie zerwane w połowie strumienia")

    session, link = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None, tts_provider=FlakyTTS())

    await session.speak("Cześć!")

    assert link.audio_chunks == [b"poczatek-"]
    assert link.control_messages == [ServerMessageType.TTS_START, ServerMessageType.TTS_END]
    # Błąd trafia do logu (sanityzacja), nie do satelity — nie ma dodatkowej ramki błędu.
    assert link.errors == []
    # Stan zostaje SPEAKING: normalne zakończenie (handle_playback_done) i tak wróci
    # do nasłuchu, gdy satelita doigra to, co dostała.
    assert session.state.name == "SPEAKING"


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
async def test_speak_returns_to_listening_when_tts_fails():
    """Bez tego sesja zostawała w SPEAKING na zawsze: `speak()` jest wołane z handlera
    `EventBus`, a ten połyka wyjątki (`shared/event_bus.py::publish`), więc błąd dostawcy
    TTS nie miał jak nigdzie wypłynąć — satelita czekała na `tts_start`, którego nigdy
    nie było, z wstrzymanym mikrofonem."""

    class ExplodingTTS(BaseTTSProvider):
        async def synthesize_stream(self, text: str):
            raise RuntimeError(f"401 Unauthorized [klucz konta {text}]")
            yield b""  # nieosiągalne — czyni funkcję generatorem, nie zwykłą korutyną

    session, link = _make_session(
        AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None, tts_provider=ExplodingTTS()
    )

    await session.speak("Cześć!")

    assert session.state.name == "LISTENING_WAKEWORD"
    assert link.control_messages == []
    assert len(link.errors) == 1
    # Sanityzacja: szczegół dostawcy zostaje w logu, nie leci do satelity.
    assert "401" not in link.errors[0]


@pytest.mark.anyio
async def test_speak_ends_turn_when_tts_returns_empty_audio():
    class SilentTTS(BaseTTSProvider):
        async def synthesize_stream(self, text: str):
            del text
            return
            yield b""  # nieosiągalne — czyni funkcję generatorem, nie zwykłą korutyną

    session, link = _make_session(
        AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None, tts_provider=SilentTTS()
    )

    await session.speak("Cześć!")

    assert session.state.name == "LISTENING_WAKEWORD"
    assert link.control_messages == [ServerMessageType.TURN_END]


@pytest.mark.anyio
async def test_end_turn_without_speech_sends_turn_end_and_returns_to_listening():
    """Tura bez tekstu do wypowiedzenia (sam tool call / samo rozumowanie) musi jawnie
    zwolnić satelitę — `turn_end`, nie `error`, bo nic się nie zepsuło."""
    session, link = _make_session(AlwaysTriggerWakeWordDetector(), on_transcript=lambda t: None)

    await session.end_turn_without_speech()

    assert session.state.name == "LISTENING_WAKEWORD"
    assert link.control_messages == [ServerMessageType.TURN_END]
    assert link.errors == []


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

    await session.reset_to_listening()

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

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        del sender_id

        async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            del arguments
            if name == "redirect_tool":
                return ToolResult(content="Przełączono.", redirect_sender_id="target_x")
            return ToolResult(is_error=True, content="nieznane narzędzie")

        return ContextBuild(
            tool_definitions=[
                ToolDefinition(name="redirect_tool", description="d", parameters={"type": "object", "properties": {}})
            ],
            system_prompt="",
            turn_context=None,
            dispatch=dispatch,
        )


class _TextOnlyMockProvider(BaseLLMProvider):
    """Zwraca jeden fragment tekstu, nigdy nie woła narzędzi."""

    def __init__(self) -> None:
        self._model = "mock-text"

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        del messages, tools, kwargs
        yield "ok"

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

@pytest.mark.anyio
async def test_redirect_changes_delivery_address_but_never_session_id():
    """Przekierowanie zmienia WYŁĄCZNIE `target_client_id` (adres dostawy); `session_id`
    (tożsamość rozmowy/pamięci) zostaje nietknięty przez całą turę.

    Wcześniej obie role pełniło jedno pole i przekierowanie przestawiało `session_id` —
    działało to tylko dla satelit, u których `session_id == sender_id`. Dla klienta,
    u którego te wartości się różnią (przeglądarka: sesja czatu vs `sender_id`), tura
    po przekierowaniu publikowała się pod tagiem, którego nikt nie słuchał, i odpowiedź
    znikała bez błędu. Ten test pilnuje, żeby te dwie role nie zrosły się z powrotem.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=_RedirectMockProvider(), memory_manager=memory_manager, world=_RedirectWorld())

        chunk_events: list[tuple[str, str, str]] = []
        done_events: list[tuple[str, str]] = []

        async def on_chunk(event: Any) -> None:
            chunk_events.append(
                (event.payload["session_id"], event.payload["target_client_id"], event.payload["chunk"])
            )

        async def on_done(event: Any) -> None:
            done_events.append((event.payload["session_id"], event.payload["target_client_id"]))

        engine.event_bus.subscribe(ServerEventType.CHAT_CHUNK, on_chunk)
        engine.event_bus.subscribe(ServerEventType.CHAT_DONE, on_done)

        # `interact_stream()` subskrybuje po "orig" — musi zobaczyć pełną turę i
        # poprawnie się zakończyć, bez dawnego dual-castu zdarzeń terminalnych.
        stream_events = [event async for event in engine.interact_stream(session_id="orig", prompt="cześć")]

        assert all(sid == "orig" for sid, _, _ in chunk_events)
        assert all(target == "target_x" for _, target, _ in chunk_events)
        assert "".join(chunk for _, _, chunk in chunk_events) == "Hello after redirect"
        # Dokładnie JEDNO zdarzenie terminalne — nie dwa (dual-cast usunięty).
        assert done_events == [("orig", "target_x")]
        assert stream_events[-1].type != "error"

        # Historia rozmowy nadal zapisana pod oryginalnym session_id — przekierowanie
        # zmienia tylko dostawę, nigdy właściciela konwersacji.
        history = memory_manager.get_history(session_id="orig")
        assert history[-1].content == "Hello after redirect"


@pytest.mark.anyio
async def test_delivery_address_defaults_to_sender_id_not_session_id():
    """Domyślny adres dostawy to `sender_id`, a nie `session_id` — dla przeglądarki te
    wartości są różne i to `sender_id` identyfikuje fizycznego klienta."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=_TextOnlyMockProvider(), memory_manager=memory_manager)

        seen: list[tuple[str, str]] = []

        async def on_chunk(event: Any) -> None:
            seen.append((event.payload["session_id"], event.payload["target_client_id"]))

        engine.event_bus.subscribe(ServerEventType.CHAT_CHUNK, on_chunk)

        _ = [e async for e in engine.interact_stream(session_id="czat_1", prompt="cześć", sender_id="browser_9")]

        assert seen
        assert all(sid == "czat_1" and target == "browser_9" for sid, target in seen)


@pytest.mark.anyio
async def test_redirect_sender_id_not_used_when_tool_does_not_redirect():
    class NoRedirectWorld:
        async def build(self, sender_id: str | None = None) -> ContextBuild:
            del sender_id

            async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
                del name, arguments
                return ToolResult(content="ok")

            return ContextBuild(
                tool_definitions=[ToolDefinition(name="redirect_tool", description="d", parameters={"type": "object", "properties": {}})],
                system_prompt="",
                turn_context=None,
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
