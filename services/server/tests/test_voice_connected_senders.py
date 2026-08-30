"""Testy śledzenia żywych połączeń WS (rejestr obecności `voice/presence.py`, współdzielony
między `gateway.py` i `routes.py`) — `sender_id` pojawia się przy połączeniu,
znika po rozłączeniu; `GET /connected` odzwierciedla ten stan."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.ai.stt import MockSTTProvider
from server.ai.tts import MockTTSProvider
from server.ai.wakeword import ThresholdEnergyWakeWordDetector
from server.config import Settings
from server.voice.gateway import create_voice_router
from server.voice.presence import ClientPresenceRegistry
from server.voice.routes import create_voice_status_router
from shared import ConfigStore, EventBus


class FakeAgentEngine:
    """Minimalny fałszywy `AgentEngine` — tylko to, czego potrzebuje `VoiceConnection`
    (subskrypcja `EventBus` i jednokierunkowe odpalenie tury), bez prawdziwego kernela."""

    def __init__(self) -> None:
        self.event_bus = EventBus()

    def start_interaction(self, **kwargs: object) -> None:
        del kwargs


def _make_client(presence: ClientPresenceRegistry, tmp_path: Path) -> TestClient:
    app = FastAPI()
    agent_engine = FakeAgentEngine()

    async def is_registered(sender_id: str) -> bool:
        del sender_id
        return True

    voice_router = create_voice_router(
        agent_engine=agent_engine,
        wakeword_detector_factory=ThresholdEnergyWakeWordDetector,
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        presence=presence,
        settings_loader=Settings,
        is_registered=is_registered,
    )
    status_router = create_voice_status_router(
        stt_provider=MockSTTProvider(),
        tts_provider=MockTTSProvider(),
        wakeword_detector_class_name=ThresholdEnergyWakeWordDetector.__name__,
        wakeword_is_placeholder=True,
        presence=presence,
        config_store=ConfigStore(Settings, tmp_path / "settings.json"),
        event_bus=agent_engine.event_bus,
    )
    app.include_router(voice_router, prefix="/ws")
    app.include_router(status_router, prefix="/api/v1/voice")
    return TestClient(app)


def test_sender_id_tracked_during_connection_and_removed_after_disconnect(tmp_path: Path) -> None:
    presence = ClientPresenceRegistry()
    client = _make_client(presence, tmp_path)

    assert presence.connected_ids() == set()
    with client.websocket_connect("/ws/voice/test_sender_1") as ws:
        ws.send_text(json.dumps({"type": "hello", "capabilities": ["mic", "speaker"]}))
        assert presence.is_connected("test_sender_1")

    assert not presence.is_connected("test_sender_1")


def test_handshake_capabilities_are_captured_and_released(tmp_path: Path) -> None:
    """Możliwości z `hello` były dotąd wyłącznie logowane — teraz trafiają do rejestru,
    z którego Web UI czyta je przy rejestracji klienta (żeby nie zgadywać jego typu),
    i znikają razem z połączeniem."""
    presence = ClientPresenceRegistry()
    client = _make_client(presence, tmp_path)

    with client.websocket_connect("/ws/voice/test_sender_1") as ws:
        ws.send_text(json.dumps({"type": "hello", "capabilities": ["mic", "speaker"]}))
        # Odbiór `client_config` (serwer odsyła je zaraz po handshake) to punkt
        # synchronizacji — bez niego asercja biegnie, zanim serwer w ogóle przeczyta
        # `hello`. Sąsiedni test tego nie potrzebuje, bo wpis o połączeniu powstaje
        # już przy samym połączeniu, przed handshake.
        assert json.loads(ws.receive_text())["type"] == "client_config"
        assert presence.capabilities_of("test_sender_1") == ["mic", "speaker"]

    # Jedno `presence.disconnect()` sprząta CAŁY ślad — to powód istnienia rejestru.
    assert presence.capabilities_of("test_sender_1") == []
    assert not presence.is_connected("test_sender_1")


def test_get_connected_reflects_presence_registry(tmp_path: Path) -> None:
    presence = ClientPresenceRegistry()
    presence.connect("sender_b")
    presence.connect("sender_a")
    presence.declare_capabilities("sender_a", ["mic", "speaker"])
    client = _make_client(presence, tmp_path)

    response = client.get("/api/v1/voice/connected")
    assert response.status_code == 200
    assert response.json() == {
        "sender_ids": ["sender_a", "sender_b"],
        "senders": [
            {"sender_id": "sender_a", "capabilities": ["mic", "speaker"]},
            {"sender_id": "sender_b", "capabilities": []},
        ],
    }
