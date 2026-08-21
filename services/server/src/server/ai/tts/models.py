from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class TTSProviderType(str, Enum):
    """Typy wspieranych dostawców TTS (UPPERCASE Enum, mirror `ai.llm.models.ProviderType`)."""

    ELEVENLABS = "ELEVENLABS"


class TTSInstanceFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji TTS (bez duplikacji ID na dysku)."""

    type: TTSProviderType = Field(description="Typ dostawcy TTS")
    name: str = Field(description="Wyświetlana nazwa instancji")
    options: dict[str, Any] = Field(default_factory=dict, description="Worek z opcjami specyficznymi dla dostawcy")


class TTSInstanceConfig(TTSInstanceFileContent):
    """Struktura instancji w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator instancji uzyskany z nazwy pliku")


class ActiveTTSBackendConfig(BaseModel):
    """Struktura pliku active_tts_backend.json przechowującego ID aktywnej instancji."""

    active_id: str = Field(description="ID aktualnie wybranego backendu TTS")
