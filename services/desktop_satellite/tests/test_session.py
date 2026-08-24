"""Testy automatu `SatelliteSession` — bez prawdziwego gniazda WS ani sprzętu
(mirror stylu `FakeLink` z `services/server/tests/test_voice_pipeline.py`)."""

from __future__ import annotations

import pytest
from desktop_satellite.session import SatelliteSession, SessionState
from shared import SatelliteMessageType, ServerMessageType


class FakeLink:
    def __init__(self) -> None:
        self.audio_chunks: list[bytes] = []
        self.control_messages: list[SatelliteMessageType] = []

    async def send_hello(self, capabilities: list[str]) -> None:
        del capabilities

    async def send_audio(self, chunk: bytes) -> None:
        self.audio_chunks.append(chunk)

    async def send_control(self, message_type: SatelliteMessageType) -> None:
        self.control_messages.append(message_type)

    async def recv(self):
        raise NotImplementedError


class FakeSpeaker:
    """Rozróżnia trzy niezależne rzeczy, dokładnie jak `SpeakerPlayback`: lokalne
    dźwięki (`play`, wołane przez `play_cue`) i strumień odpowiedzi TTS
    (`start_stream`/`write_chunk`/`stop_stream`) — mieszanie ich w jednej liście
    ukrywałoby błędy kolejności (np. `write_chunk` wywołane bez `start_stream`)."""

    def __init__(self) -> None:
        self.played: list[bytes] = []
        self.cues: list[str] = []
        self.streamed_chunks: list[bytes] = []
        self.stream_open = False
        self.stream_started_count = 0
        self.stream_stopped_count = 0

    async def play(self, pcm_audio: bytes) -> None:
        self.played.append(pcm_audio)

    async def play_cue(self, windows_sound_name: str, fallback_pcm: bytes) -> None:
        self.cues.append(windows_sound_name)
        self.played.append(fallback_pcm)

    async def start_stream(self) -> None:
        self.stream_open = True
        self.stream_started_count += 1

    async def write_chunk(self, pcm_audio: bytes) -> None:
        assert self.stream_open, "write_chunk() wywołane bez uprzedniego start_stream()."
        self.streamed_chunks.append(pcm_audio)

    async def stop_stream(self) -> None:
        self.stream_open = False
        self.stream_stopped_count += 1


class AlwaysTriggerVad:
    def process(self, pcm_chunk: bytes) -> bool:
        del pcm_chunk
        return True

    def reset(self) -> None:
        pass


class NeverTriggerVad:
    def process(self, pcm_chunk: bytes) -> bool:
        del pcm_chunk
        return False

    def reset(self) -> None:
        pass


def _make_session(vad) -> tuple[SatelliteSession, FakeLink, FakeSpeaker]:
    """Testy tu wołają metody automatu bezpośrednio (nie `run()`, które czeka na
    `CLIENT_CONFIG` od serwera przed ustawieniem `_vad`) — podstawiamy gotowy `vad`
    wprost, `vad_factory` nigdy nie zostanie faktycznie wywołane w tych testach."""
    link = FakeLink()
    speaker = FakeSpeaker()
    session = SatelliteSession(link=link, speaker=speaker, vad_factory=lambda *_: vad)
    session._vad = vad
    return session, link, speaker


@pytest.mark.anyio
async def test_mic_frame_in_listening_only_streams_audio() -> None:
    session, link, _ = _make_session(NeverTriggerVad())
    await session.handle_mic_frame(b"\x01\x02")
    assert link.audio_chunks == [b"\x01\x02"]
    assert session.state == SessionState.LISTENING_WAKEWORD


@pytest.mark.anyio
async def test_wake_detected_transitions_to_recording_and_plays_tone() -> None:
    session, _, speaker = _make_session(NeverTriggerVad())
    await session.handle_server_frame({"type": ServerMessageType.WAKE_DETECTED.value})
    assert session.state == SessionState.RECORDING_UTTERANCE
    assert len(speaker.played) == 1
    assert speaker.cues == ["Speech On"]


@pytest.mark.anyio
async def test_vad_trigger_sends_utterance_end_and_moves_to_processing() -> None:
    session, link, _ = _make_session(AlwaysTriggerVad())
    session.state = SessionState.RECORDING_UTTERANCE
    await session.handle_mic_frame(b"\x03\x04")
    assert link.audio_chunks == [b"\x03\x04"]
    assert link.control_messages == [SatelliteMessageType.UTTERANCE_END]
    assert session.state == SessionState.PROCESSING


@pytest.mark.anyio
async def test_mic_frames_ignored_while_processing() -> None:
    session, link, _ = _make_session(NeverTriggerVad())
    session.state = SessionState.PROCESSING
    await session.handle_mic_frame(b"\x05\x06")
    assert link.audio_chunks == []
    assert session.state == SessionState.PROCESSING


@pytest.mark.anyio
async def test_full_tts_cycle_streams_audio_and_returns_to_listening() -> None:
    """Fragmenty graja W MIARE NADEJSCIA (przez otwarty strumien), nie po dograniu sie
    calej odpowiedzi do jednego bufora — sedno streamingu TTS: `write_chunk` musi
    zobaczyc kazdy fragment OSOBNO, w kolejnosci przyjscia, a strumien musi byc otwarty
    (`start_stream`) juz na `tts_start`, zanim przyjdzie pierwsza ramka binarna."""
    session, link, speaker = _make_session(NeverTriggerVad())
    session.state = SessionState.PROCESSING

    await session.handle_server_frame({"type": ServerMessageType.PLAY_STOP_TONE.value})
    assert len(speaker.played) == 1  # stop-tone
    assert speaker.cues == ["Speech Sleep"]

    await session.handle_server_frame({"type": ServerMessageType.TTS_START.value})
    assert session.state == SessionState.SPEAKING
    assert speaker.stream_started_count == 1

    await session.handle_server_frame(b"chunk1")
    await session.handle_server_frame(b"chunk2")
    # Strumien pozostaje otwarty MIEDZY fragmentami — jeszcze nie zamkniety.
    assert speaker.stream_open is True

    await session.handle_server_frame({"type": ServerMessageType.TTS_END.value})
    assert speaker.streamed_chunks == [b"chunk1", b"chunk2"]
    assert speaker.stream_stopped_count == 1
    assert speaker.stream_open is False
    assert link.control_messages == [SatelliteMessageType.PLAYBACK_DONE]
    assert session.state == SessionState.LISTENING_WAKEWORD


@pytest.mark.anyio
async def test_turn_end_frame_returns_to_listening_without_sound() -> None:
    """Tura bez odpowiedzi głosowej (serwer: `end_turn_without_speech`) zwalnia satelitę
    natychmiast. Bez tej ramki satelita czekałaby na `tts_start`, który nigdy nie
    przyjdzie — z wstrzymanym mikrofonem, czyli trwale głucha.

    Cisza jest tu zamierzona: nic się nie zepsuło, więc żaden dźwięk nie ma prawa zagrać
    (to nie jest `error`) i nie wysyłamy `playback_done` — nie było czego odtwarzać."""
    session, link, speaker = _make_session(NeverTriggerVad())
    session.state = SessionState.PROCESSING

    await session.handle_server_frame({"type": ServerMessageType.TURN_END.value})

    assert session.state == SessionState.LISTENING_WAKEWORD
    assert speaker.played == []
    assert speaker.cues == []
    assert link.control_messages == []


@pytest.mark.anyio
async def test_error_frame_resets_to_listening() -> None:
    session, _, _ = _make_session(NeverTriggerVad())
    session.state = SessionState.RECORDING_UTTERANCE
    await session.handle_server_frame({"type": ServerMessageType.ERROR.value, "detail": "boom"})
    assert session.state == SessionState.LISTENING_WAKEWORD


@pytest.mark.anyio
async def test_binary_frame_ignored_outside_speaking_state() -> None:
    session, _, speaker = _make_session(NeverTriggerVad())
    session.state = SessionState.LISTENING_WAKEWORD
    await session.handle_server_frame(b"stray-audio")
    assert speaker.played == []
    assert speaker.streamed_chunks == []


class ConfigLink(FakeLink):
    """`FakeLink` z konfigurowalnym pierwszym odebranym frame'm — do testowania
    `_await_client_config()` bez wchodzenia w `run()`'s nieskończone pompy."""

    def __init__(self, first_frame) -> None:
        super().__init__()
        self._first_frame = first_frame

    async def recv(self):
        return self._first_frame


@pytest.mark.anyio
async def test_await_client_config_applies_server_values() -> None:
    link = ConfigLink({"type": "client_config", "silence_duration_ms": 900.0, "amplitude_threshold": 700})
    speaker = FakeSpeaker()
    captured: list[tuple[float, int]] = []

    def vad_factory(silence_ms: float, amplitude: int) -> NeverTriggerVad:
        captured.append((silence_ms, amplitude))
        return NeverTriggerVad()

    session = SatelliteSession(link=link, speaker=speaker, vad_factory=vad_factory)
    vad = await session._await_client_config()

    assert captured == [(900.0, 700)]
    assert vad is not None


@pytest.mark.anyio
async def test_await_client_config_falls_back_on_unexpected_frame() -> None:
    link = ConfigLink({"type": "wake_detected"})
    speaker = FakeSpeaker()
    captured: list[tuple[float, int]] = []

    def vad_factory(silence_ms: float, amplitude: int) -> NeverTriggerVad:
        captured.append((silence_ms, amplitude))
        return NeverTriggerVad()

    session = SatelliteSession(link=link, speaker=speaker, vad_factory=vad_factory)
    await session._await_client_config()

    assert captured == [(1500.0, 500)]


@pytest.mark.anyio
async def test_await_client_config_falls_back_on_timeout(monkeypatch) -> None:
    class NeverRespondsLink(FakeLink):
        async def recv(self):
            import asyncio

            await asyncio.sleep(10)
            raise AssertionError("nieosiągalne")

    import desktop_satellite.session as session_module

    monkeypatch.setattr(session_module, "CLIENT_CONFIG_TIMEOUT_SECONDS", 0.05)

    link = NeverRespondsLink()
    speaker = FakeSpeaker()
    captured: list[tuple[float, int]] = []

    def vad_factory(silence_ms: float, amplitude: int) -> NeverTriggerVad:
        captured.append((silence_ms, amplitude))
        return NeverTriggerVad()

    session = SatelliteSession(link=link, speaker=speaker, vad_factory=vad_factory)
    await session._await_client_config()

    assert captured == [(1500.0, 500)]
