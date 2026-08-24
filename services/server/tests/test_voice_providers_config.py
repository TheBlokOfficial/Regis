"""Testy legacy configu dostawców STT/TTS (`server/ai/legacy_config.py`).

Plik `data/voice/config.json` pochodzi sprzed wprowadzenia rejestrów wielu
instancji (`STTRegistry`/`TTSRegistry`) i **nie jest już zapisywany przez żadną
ścieżkę aplikacji** — zostaje wyłącznie jako źródło jednorazowej migracji kluczy
API do rejestru (`ai/stt/registry.py`, `ai/tts/registry.py`). Te testy pilnują
kontraktu odczytu, na którym ta migracja stoi.

Testy płaskiego shimu `GET/PUT /api/v1/voice/providers/config` zostały usunięte
razem z samym shimem — jego jedyny konsument (`voice_config.js`) przeszedł na
pełny CRUD w zakładce Dostawcy, a endpoint pozostawał martwy.
"""

from __future__ import annotations

import pytest
from server.ai.legacy_config import VoiceProvidersConfig, load_voice_providers_config, save_voice_providers_config


@pytest.fixture
def voice_config_path(monkeypatch, tmp_path):
    path = tmp_path / "voice" / "config.json"
    monkeypatch.setattr("server.ai.legacy_config._CONFIG_PATH", path)
    return path


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
