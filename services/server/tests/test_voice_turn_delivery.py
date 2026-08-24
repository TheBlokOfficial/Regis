"""Doręczenie tury do satelity — co trafia do mowy i czym kończy się każda tura.

Dwa niezależne błędy z jednej sesji, oba objawiające się tak samo (satelita zawieszona
w stanie przetwarzania, z wstrzymanym mikrofonem, do restartu):

1. bufor mowy zbierał WSZYSTKO ze strumienia, więc agent czytał na głos własny
   chain of thought — a im dłuższy tekst, tym dłuższa synteza i "zwiecha";
2. tura bez tekstu do wypowiedzenia kończyła się gołym `return` w `_on_done`, więc
   nic nigdy nie zwalniało sesji z `PROCESSING`.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from server.ai.stt import MockSTTProvider
from server.config import Settings
from server.events import ServerEventType
from server.voice.gateway import VoiceConnection
from server.voice.tts import BaseTTSProvider
from server.voice.wakeword import ThresholdEnergyWakeWordDetector
from shared import Event, EventBus, ServerMessageType

SENDER = "snd_gateway"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class FakeWebSocket:
    """Tylko to, czego `VoiceConnection` używa jako `SatelliteLink`."""

    def __init__(self) -> None:
        self.text_frames: list[dict[str, Any]] = []
        self.binary_frames: list[bytes] = []

    async def send_text(self, data: str) -> None:
        self.text_frames.append(json.loads(data))

    async def send_bytes(self, data: bytes) -> None:
        self.binary_frames.append(data)

    def frame_types(self) -> list[str]:
        return [frame["type"] for frame in self.text_frames]


class EchoTTS(BaseTTSProvider):
    def __init__(self) -> None:
        self.synthesized: list[str] = []

    async def synthesize_stream(self, text: str):
        self.synthesized.append(text)
        yield f"audio:{text}".encode()


class FakeAgentEngine:
    def __init__(self) -> None:
        self.event_bus = EventBus()

    def start_interaction(self, **kwargs: object) -> None:
        del kwargs


def _make_connection(tts: BaseTTSProvider | None = None) -> tuple[VoiceConnection, FakeWebSocket]:
    websocket = FakeWebSocket()
    connection = VoiceConnection(
        sender_id=SENDER,
        websocket=websocket,  # type: ignore[arg-type]
        agent_engine=FakeAgentEngine(),  # type: ignore[arg-type]
        wakeword_detector=ThresholdEnergyWakeWordDetector(),
        stt_provider=MockSTTProvider(),
        tts_provider=tts or EchoTTS(),
        settings_loader=Settings,
        sender_states={},
        pending_capabilities={},
        is_registered=_always_registered,
    )
    return connection, websocket


async def _always_registered(sender_id: str) -> bool:
    del sender_id
    return True


def _chunk_event(chunk: str, kind: str) -> Event[Any]:
    return Event(
        type=ServerEventType.CHAT_CHUNK,
        payload={"session_id": SENDER, "target_client_id": SENDER, "chunk": chunk, "kind": kind},
        sender="agent_engine",
    )


def _done_event() -> Event[Any]:
    return Event(
        type=ServerEventType.CHAT_DONE,
        payload={"session_id": SENDER, "target_client_id": SENDER},
        sender="agent_engine",
    )


@pytest.mark.anyio
async def test_reasoning_chunks_never_reach_the_speech_buffer() -> None:
    tts = EchoTTS()
    connection, _ = _make_connection(tts)

    await connection._on_chunk(_chunk_event("Zastanawiam się, czy ", "reasoning"))
    await connection._on_chunk(_chunk_event("użytkownik chce światła.", "reasoning"))
    await connection._on_chunk(_chunk_event("Włączyłem światło.", "answer"))
    await connection._on_done(_done_event())
    await connection._speak_task

    assert tts.synthesized == ["Włączyłem światło."]


@pytest.mark.anyio
async def test_turn_with_only_reasoning_ends_without_speech() -> None:
    """Po rozdzieleniu rozumowania ten przypadek stał się CZĘSTSZY: tura złożona z samego
    myślenia zostawia pusty bufor mowy. Musi kończyć się `turn_end`, nie ciszą."""
    tts = EchoTTS()
    connection, websocket = _make_connection(tts)

    await connection._on_chunk(_chunk_event("Same rozważania.", "reasoning"))
    await connection._on_done(_done_event())

    assert tts.synthesized == []
    assert websocket.frame_types() == [ServerMessageType.TURN_END.value]
    assert connection.session.state.name == "LISTENING_WAKEWORD"


@pytest.mark.anyio
async def test_answer_turn_sends_full_tts_sequence() -> None:
    connection, websocket = _make_connection()

    await connection._on_chunk(_chunk_event("Gotowe.", "answer"))
    await connection._on_done(_done_event())
    await connection._speak_task

    assert websocket.frame_types() == [ServerMessageType.TTS_START.value, ServerMessageType.TTS_END.value]
    assert websocket.binary_frames == [b"audio:Gotowe."]


@pytest.mark.anyio
async def test_speech_buffer_is_cleared_between_turns() -> None:
    tts = EchoTTS()
    connection, _ = _make_connection(tts)

    await connection._on_chunk(_chunk_event("Pierwsza.", "answer"))
    await connection._on_done(_done_event())
    await connection._speak_task

    await connection.session.handle_playback_done()

    await connection._on_chunk(_chunk_event("Druga.", "answer"))
    await connection._on_done(_done_event())
    await connection._speak_task

    assert tts.synthesized == ["Pierwsza.", "Druga."]
