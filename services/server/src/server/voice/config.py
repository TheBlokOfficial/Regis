"""Konfiguracja dostawców chmurowych STT/TTS (Groq/ElevenLabs) — pojedynczy plik
JSON, mirror wzorca `HomeAssistantConfig`/`WorldEngine` (singleton, `ConfigStore`).

Puste `*_api_key` = brak konfiguracji, `main.py` degraduje się łagodnie do
`MockSTTProvider`/`MockTTSProvider` (ten sam wzorzec co Home Assistant i
`Settings.wakeword_model_path`) — bez osobnego przełącznika `enabled`.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel
from shared import ConfigStore, get_service_root

GroqSttModel = Literal["whisper-large-v3-turbo", "whisper-large-v3"]

# "Adam" — domyślny, wbudowany głos ElevenLabs, zweryfikowany zapytaniem do
# GET /v1/voices (nie zgadywany z pamięci).
DEFAULT_ELEVENLABS_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
# Jedyny model ElevenLabs jawnie potwierdzony (dokumentacja) jako wspierający
# polski w kontekście multilingual TTS.
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_multilingual_v2"


class VoiceProvidersConfig(BaseModel):
    """Konfiguracja singletona dostawców STT/TTS."""

    groq_api_key: str = ""
    groq_stt_model: GroqSttModel = "whisper-large-v3-turbo"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = DEFAULT_ELEVENLABS_VOICE_ID
    elevenlabs_model_id: str = DEFAULT_ELEVENLABS_MODEL_ID


_CONFIG_PATH = get_service_root(__file__) / "data" / "voice" / "config.json"


async def load_voice_providers_config() -> VoiceProvidersConfig:
    """Wczytuje config (tworzy plik z wartościami domyślnymi przy pierwszym uruchomieniu)."""
    return await asyncio.to_thread(ConfigStore(VoiceProvidersConfig, _CONFIG_PATH).load)


async def save_voice_providers_config(config: VoiceProvidersConfig) -> None:
    await asyncio.to_thread(ConfigStore(VoiceProvidersConfig, _CONFIG_PATH).save, config)
