"""DTO warstwy REST domeny Voice — prywatne słownictwo, nie w `shared/contracts.py`
(mirror `world/dto.py`: nie ma potrzeby generycznego kształtu skoro istnieje
dokładnie jeden zestaw dostawców — Groq/ElevenLabs)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from server.voice.config import GroqSttModel


class VoiceProvidersConfigDTO(BaseModel):
    """Config dostawców STT/TTS — klucze API zawsze zamaskowane (patrz `_mask_key`
    w `routes.py`)."""

    groq_api_key: str = Field(..., description="Klucz API Groq, zamaskowany")
    groq_stt_model: GroqSttModel
    elevenlabs_api_key: str = Field(..., description="Klucz API ElevenLabs, zamaskowany")
    elevenlabs_voice_id: str
    elevenlabs_model_id: str


class UpdateVoiceProvidersConfigRequest(BaseModel):
    """Puste/brak `*_api_key` = zachowaj obecnie zapisany klucz (frontend nigdy nie
    zna prawdziwej wartości — `GET .../config` zwraca ją zawsze zamaskowaną, ten sam
    wzorzec co `UpdateHomeAssistantConfigRequest`). Pozostałe pola nie są sekretami —
    frontend zawsze zna i odsyła ich bieżącą wartość, więc są wymagane."""

    groq_api_key: str | None = Field(None, description="Puste/brak = zachowaj obecny klucz")
    groq_stt_model: GroqSttModel
    elevenlabs_api_key: str | None = Field(None, description="Puste/brak = zachowaj obecny klucz")
    elevenlabs_voice_id: str
    elevenlabs_model_id: str
