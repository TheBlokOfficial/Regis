"""Testy dashboardu "Klienci" (Web UI): `GET /clients/status` (snapshot) i
`GET /clients/watch` (SSE, mirror `AgentEngine.watch_session()`/chat's
`.../sessions/{id}/watch` — pasywna, globalna, nigdy się nie kończy sama)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from shared import ConfigStore, Event, EventBus

from server.config import Settings
from server.voice.events import VoiceEventType
from server.voice.routes import create_voice_status_router


def _make_client(tmp_path: Path, sender_states: dict[str, str], event_bus: EventBus) -> TestClient:
    app = FastAPI()
    router = create_voice_status_router(
        stt_provider=None,
        tts_provider=None,
        wakeword_detector_class_name="OnnxWakeWordDetector",
        connected_sender_ids=set(),
        config_store=ConfigStore(Settings, tmp_path / "settings.json"),
        sender_states=sender_states,
        event_bus=event_bus,
        pending_capabilities={},
    )
    app.include_router(router, prefix="/api/v1/voice")
    return TestClient(app)


def test_clients_status_returns_snapshot(tmp_path: Path) -> None:
    sender_states = {"sat_1": "LISTENING_WAKEWORD", "sat_2": "PROCESSING"}
    client = _make_client(tmp_path, sender_states, EventBus())

    res = client.get("/api/v1/voice/clients/status")
    assert res.status_code == 200
    assert res.json() == {"states": {"sat_1": "LISTENING_WAKEWORD", "sat_2": "PROCESSING"}}


@pytest.mark.anyio
async def test_watch_voice_events_forwards_events_and_does_not_terminate() -> None:
    """Mirror `test_watch_session_forwards_user_message_and_does_not_terminate`
    (chat) — subskrypcja jest globalna (nie per-sender_id), więc żadne zdarzenie
    voice nie jest filtrowane; generator nigdy się nie kończy sam na 'disconnected'."""
    from server.voice.routes import watch_voice_events

    event_bus = EventBus()
    watcher = watch_voice_events(event_bus)

    first_task = asyncio.ensure_future(anext(watcher))
    await asyncio.sleep(0)  # pozwól generatorowi zdazyc zasubskrybowac przed publikacja
    await event_bus.publish(
        Event(type=VoiceEventType.SATELLITE_CONNECTED, payload={"sender_id": "sat_1"}, sender="voice")
    )
    first = await first_task
    assert first.type == VoiceEventType.SATELLITE_CONNECTED

    await event_bus.publish(
        Event(
            type=VoiceEventType.SATELLITE_WAKE_WORD_DETECTED,
            payload={"sender_id": "sat_1", "score": 0.72},
            sender="voice",
        )
    )
    second = await anext(watcher)
    assert second.type == VoiceEventType.SATELLITE_WAKE_WORD_DETECTED
    assert second.payload["score"] == 0.72

    # Kluczowe: 'disconnected' NIE kończy generatora — to obserwator (SSE) decyduje.
    await event_bus.publish(
        Event(type=VoiceEventType.SATELLITE_DISCONNECTED, payload={"sender_id": "sat_1"}, sender="voice")
    )
    third = await anext(watcher)
    assert third.type == VoiceEventType.SATELLITE_DISCONNECTED
    assert watcher.ag_frame is not None

    await watcher.aclose()
