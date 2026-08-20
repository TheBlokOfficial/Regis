"""Testy automatu `SatelliteSession` — bez prawdziwego gniazda WS ani sprzętu
(mirror stylu `FakeLink` z `services/server/tests/test_voice_pipeline.py`)."""

from __future__ import annotations

import pytest

from shared import SatelliteMessageType, ServerMessageType

from desktop_satellite.session import SatelliteSession, SessionState


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
    def __init__(self) -> None:
        self.played: list[bytes] = []
        self.cues: list[str] = []

    async def play(self, pcm_audio: bytes) -> None:
        self.played.append(pcm_audio)

    async def play_cue(self, windows_sound_name: str, fallback_pcm: bytes) -> None:
        self.cues.append(windows_sound_name)
        self.played.append(fallback_pcm)


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
    link = FakeLink()
    speaker = FakeSpeaker()
    session = SatelliteSession(link=link, speaker=speaker, vad=vad)
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
async def test_full_tts_cycle_plays_audio_and_returns_to_listening() -> None:
    session, link, speaker = _make_session(NeverTriggerVad())
    session.state = SessionState.PROCESSING

    await session.handle_server_frame({"type": ServerMessageType.PLAY_STOP_TONE.value})
    assert len(speaker.played) == 1  # stop-tone
    assert speaker.cues == ["Speech Sleep"]

    await session.handle_server_frame({"type": ServerMessageType.TTS_START.value})
    assert session.state == SessionState.SPEAKING

    await session.handle_server_frame(b"chunk1")
    await session.handle_server_frame(b"chunk2")

    await session.handle_server_frame({"type": ServerMessageType.TTS_END.value})
    assert speaker.played[-1] == b"chunk1chunk2"
    assert link.control_messages == [SatelliteMessageType.PLAYBACK_DONE]
    assert session.state == SessionState.LISTENING_WAKEWORD


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
