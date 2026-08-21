"""CRUD dostawców STT/TTS (`STTRegistry`/`TTSRegistry`, `STTFactory`/`TTSFactory`,
REST `voice/provider_routes.py`) — mirror `test_llm_providers.py` (LLM)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.ai.stt import GroqSTTProvider, MockSTTProvider, STTFactory, STTInstanceConfig, STTProviderType, STTRegistry
from server.ai.tts import ElevenLabsTTSProvider, MockTTSProvider, TTSFactory, TTSInstanceConfig, TTSProviderType, TTSRegistry
from server.voice.provider_routes import create_voice_providers_router


def test_stt_factory_creates_groq_provider():
    config = STTInstanceConfig(
        id="stt_test", type=STTProviderType.GROQ, name="Test", options={"api_key": "gsk_x", "model": "whisper-large-v3"}
    )
    provider = STTFactory.create_provider(config)
    assert isinstance(provider, GroqSTTProvider)


def test_stt_factory_degrades_to_mock_when_api_key_empty():
    config = STTInstanceConfig(id="stt_test", type=STTProviderType.GROQ, name="Test", options={"api_key": ""})
    provider = STTFactory.create_provider(config)
    assert isinstance(provider, MockSTTProvider)


def test_stt_factory_schemas_include_api_key_and_model():
    schemas = STTFactory.get_all_schemas()
    assert len(schemas.provider_types) == 1
    opt_names = [opt.name for opt in schemas.provider_types[0].options_schema]
    assert "api_key" in opt_names
    assert "model" in opt_names


def test_tts_factory_creates_elevenlabs_provider():
    config = TTSInstanceConfig(
        id="tts_test",
        type=TTSProviderType.ELEVENLABS,
        name="Test",
        options={"api_key": "sk_x", "voice_id": "v1", "model_id": "eleven_multilingual_v2"},
    )
    provider = TTSFactory.create_provider(config)
    assert isinstance(provider, ElevenLabsTTSProvider)


def test_tts_factory_degrades_to_mock_when_api_key_empty():
    config = TTSInstanceConfig(id="tts_test", type=TTSProviderType.ELEVENLABS, name="Test", options={"api_key": ""})
    provider = TTSFactory.create_provider(config)
    assert isinstance(provider, MockTTSProvider)


def test_tts_factory_schemas_include_api_key_voice_and_model():
    schemas = TTSFactory.get_all_schemas()
    assert len(schemas.provider_types) == 1
    opt_names = [opt.name for opt in schemas.provider_types[0].options_schema]
    assert {"api_key", "voice_id", "model_id"} <= set(opt_names)


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(
        create_voice_providers_router(
            stt_registry=STTRegistry(data_dir=tmp_path),
            tts_registry=TTSRegistry(data_dir=tmp_path),
        ),
        prefix="/api/v1/voice",
    )
    return TestClient(app)


def test_stt_providers_list_has_seeded_default(client) -> None:
    response = client.get("/api/v1/voice/stt/providers")
    assert response.status_code == 200
    data = response.json()
    assert data["active_id"] == "stt_groq_default"
    assert len(data["providers"]) == 1
    assert data["providers"][0]["is_active"] is True


def test_stt_providers_create_list_switch_delete(client) -> None:
    create_resp = client.post(
        "/api/v1/voice/stt/providers",
        json={"type": "GROQ", "name": "Local Whisper (placeholder)", "options": {"api_key": "gsk_abcdef1234", "model": "whisper-large-v3"}},
    )
    assert create_resp.status_code == 201
    new_id = create_resp.json()["id"]
    assert create_resp.json()["options"]["api_key"].startswith("•")

    switch_resp = client.put("/api/v1/voice/stt/providers/active", json={"provider_id": new_id})
    assert switch_resp.status_code == 200
    assert switch_resp.json()["active_id"] == new_id

    # Nie można usunąć aktywnej instancji.
    delete_active = client.delete(f"/api/v1/voice/stt/providers/{new_id}")
    assert delete_active.status_code == 400

    # Przełącz z powrotem i usuń nowo utworzoną.
    client.put("/api/v1/voice/stt/providers/active", json={"provider_id": "stt_groq_default"})
    delete_resp = client.delete(f"/api/v1/voice/stt/providers/{new_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["deleted_id"] == new_id


def test_tts_providers_list_has_seeded_default(client) -> None:
    response = client.get("/api/v1/voice/tts/providers")
    assert response.status_code == 200
    data = response.json()
    assert data["active_id"] == "tts_elevenlabs_default"
    assert len(data["providers"]) == 1


def test_tts_providers_create_switch(client) -> None:
    create_resp = client.post(
        "/api/v1/voice/tts/providers",
        json={"type": "ELEVENLABS", "name": "Local TTS (placeholder)", "options": {"api_key": "sk_abcdef1234"}},
    )
    assert create_resp.status_code == 201
    new_id = create_resp.json()["id"]

    switch_resp = client.put("/api/v1/voice/tts/providers/active", json={"provider_id": new_id})
    assert switch_resp.status_code == 200
    assert switch_resp.json()["active_id"] == new_id
