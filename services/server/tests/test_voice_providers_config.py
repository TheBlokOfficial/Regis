"""Testy configu dostawców STT/TTS (`server/voice/config.py`) i endpointów REST
`GET/PUT /api/v1/voice/providers/config` (`server/voice/routes.py`) — maskowanie
kluczy API na odczyt, "puste pole = zachowaj obecny klucz" na zapis (mirror wzorca
`HomeAssistantConfig`/`world/routes.py`)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.voice.config import VoiceProvidersConfig, load_voice_providers_config, save_voice_providers_config
from server.voice.routes import create_voice_status_router
from server.voice.stt import MockSTTProvider
from server.voice.tts import MockTTSProvider


@pytest.fixture
def voice_config_path(monkeypatch, tmp_path):
    path = tmp_path / "voice" / "config.json"
    monkeypatch.setattr("server.voice.config._CONFIG_PATH", path)
    return path


@pytest.fixture
def client(voice_config_path):
    app = FastAPI()
    app.include_router(
        create_voice_status_router(
            stt_provider=MockSTTProvider(),
            tts_provider=MockTTSProvider(),
            wakeword_detector_class_name="ThresholdEnergyWakeWordDetector",
            connected_sender_ids=set(),
        ),
        prefix="/api/v1/voice",
    )
    return TestClient(app)


@pytest.mark.anyio
async def test_config_round_trip(voice_config_path) -> None:
    config = VoiceProvidersConfig(groq_api_key="sk-test-key", groq_stt_model="whisper-large-v3")
    await save_voice_providers_config(config)
    loaded = await load_voice_providers_config()
    assert loaded.groq_api_key == "sk-test-key"
    assert loaded.groq_stt_model == "whisper-large-v3"


@pytest.mark.anyio
async def test_config_defaults_on_first_load(voice_config_path) -> None:
    config = await load_voice_providers_config()
    assert config.groq_api_key == ""
    assert config.groq_stt_model == "whisper-large-v3-turbo"
    assert config.elevenlabs_voice_id == "pNInz6obpgDQGcFmaJgB"
    assert config.elevenlabs_model_id == "eleven_multilingual_v2"


def test_get_providers_config_masks_empty_key_as_empty(client) -> None:
    response = client.get("/api/v1/voice/providers/config")
    assert response.status_code == 200
    data = response.json()
    assert data["groq_api_key"] == ""
    assert data["elevenlabs_api_key"] == ""


def test_put_then_get_returns_masked_key(client) -> None:
    put_response = client.put(
        "/api/v1/voice/providers/config",
        json={
            "groq_api_key": "sk-1234567890abcdef",
            "groq_stt_model": "whisper-large-v3",
            "elevenlabs_api_key": None,
            "elevenlabs_voice_id": "custom_voice_id",
            "elevenlabs_model_id": "eleven_multilingual_v2",
        },
    )
    assert put_response.status_code == 200

    get_response = client.get("/api/v1/voice/providers/config")
    data = get_response.json()
    assert data["groq_api_key"].endswith("cdef")
    assert data["groq_api_key"].startswith("•")
    assert data["groq_stt_model"] == "whisper-large-v3"
    assert data["elevenlabs_voice_id"] == "custom_voice_id"


def test_put_empty_api_key_preserves_existing_key(client) -> None:
    client.put(
        "/api/v1/voice/providers/config",
        json={
            "groq_api_key": "sk-original-key-value",
            "groq_stt_model": "whisper-large-v3-turbo",
            "elevenlabs_api_key": None,
            "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
            "elevenlabs_model_id": "eleven_multilingual_v2",
        },
    )

    # Druga aktualizacja bez klucza -> zachowuje poprzedni, ale pozostałe pola się zmieniają.
    client.put(
        "/api/v1/voice/providers/config",
        json={
            "groq_api_key": None,
            "groq_stt_model": "whisper-large-v3",
            "elevenlabs_api_key": None,
            "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",
            "elevenlabs_model_id": "eleven_multilingual_v2",
        },
    )

    data = client.get("/api/v1/voice/providers/config").json()
    assert data["groq_api_key"].endswith("alue")
    assert data["groq_stt_model"] == "whisper-large-v3"
