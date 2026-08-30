"""LEGACY: jednoslotowa konfiguracja dostawców STT/TTS sprzed rejestrów instancji.

Plik `data/voice/config.json` był jedynym miejscem na klucze Groq/ElevenLabs, zanim
`STTRegistry`/`TTSRegistry` wprowadziły wiele nazwanych instancji. Dziś ten moduł
istnieje **wyłącznie** po to, żeby `_ensure_default_instances()` w obu rejestrach
mogło przy pierwszym uruchomieniu przenieść istniejące klucze użytkownika do nowego
formatu, zamiast je zgubić.

Mieszka w `server.ai`, nie w `server.voice`, bo migracja jest sprawą warstwy
konkretów AI (to ona czyta i zapisuje instancje) — `voice/` nie ma z nim już
żadnego kontaktu. Do usunięcia razem z blokiem migracji, gdy okno migracyjne
zostanie uznane za zamknięte.
"""

from __future__ import annotations

import asyncio
from typing import Literal

from pydantic import BaseModel
from shared import ConfigStore, data_dir

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


_CONFIG_PATH = data_dir(__file__) / "voice" / "config.json"


async def load_voice_providers_config() -> VoiceProvidersConfig:
    """Wczytuje config (tworzy plik z wartościami domyślnymi przy pierwszym uruchomieniu)."""
    return await asyncio.to_thread(ConfigStore(VoiceProvidersConfig, _CONFIG_PATH).load)


async def save_voice_providers_config(config: VoiceProvidersConfig) -> None:
    await asyncio.to_thread(ConfigStore(VoiceProvidersConfig, _CONFIG_PATH).save, config)
