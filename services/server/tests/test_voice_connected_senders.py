"""Testy śledzenia żywych połączeń WS (`connected_sender_ids`, współdzielony
między `gateway.py` i `routes.py`) — `sender_id` pojawia się przy połączeniu,
znika po rozłączeniu; `GET /connected` odzwierciedla ten stan."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared import EventBus

from server.voice.gateway import create_voice_router
from server.voice.routes import create_voice_status_router
from server.voice.stt import MockSTTProvider
from server.voice.tts import MockTTSProvider
from server.voice.wakeword import ThresholdEnergyWakeWordDetector


class FakeAgentEngine:
    """Minimalny fałszywy `AgentEngine` — tylko to, czego potrzebuje `VoiceConnection`
    (subskrypcja `EventBus` i jednokierunkowe odpalenie tury), bez prawdziwego kernela."""

    def __init__(self) -> None:
        self.event_bus = EventBus()

    def start_interaction(self, **kwargs: object) -> None:
        del kwargs


def _make_client(connected_sender_ids: set[str]) -> TestClient:
    app = FastAPI()
    voice_router = create_voice_router(
        agent_engine=FakeAgentEngine(),
        wakeword_detector_factory=ThresholdEnergyWakeWordDetector,
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        connected_sender_ids=connected_sender_ids,
    )
    status_router = create_voice_status_router(
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        wakeword_detector_class_name=ThresholdEnergyWakeWordDetector.__name__,
        connected_sender_ids=connected_sender_ids,
    )
    app.include_router(voice_router, prefix="/ws")
    app.include_router(status_router, prefix="/api/v1/voice")
    return TestClient(app)


def test_sender_id_tracked_during_connection_and_removed_after_disconnect() -> None:
    connected: set[str] = set()
    client = _make_client(connected)

    assert connected == set()
    with client.websocket_connect("/ws/voice/test_sender_1") as ws:
        ws.send_text(json.dumps({"type": "hello", "capabilities": ["mic", "speaker"]}))
        assert "test_sender_1" in connected

    assert "test_sender_1" not in connected


def test_get_connected_reflects_shared_set() -> None:
    connected: set[str] = {"sender_b", "sender_a"}
    client = _make_client(connected)

    response = client.get("/api/v1/voice/connected")
    assert response.status_code == 200
    assert response.json() == {"sender_ids": ["sender_a", "sender_b"]}
