from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class STTProviderType(str, Enum):
    """Typy wspieranych dostawców STT (UPPERCASE Enum, mirror `ai.llm.models.ProviderType`)."""

    GROQ = "GROQ"


class STTInstanceFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji STT (bez duplikacji ID na dysku)."""

    type: STTProviderType = Field(description="Typ dostawcy STT")
    name: str = Field(description="Wyświetlana nazwa instancji")
    options: dict[str, Any] = Field(default_factory=dict, description="Worek z opcjami specyficznymi dla dostawcy")


class STTInstanceConfig(STTInstanceFileContent):
    """Struktura instancji w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator instancji uzyskany z nazwy pliku")


class ActiveSTTBackendConfig(BaseModel):
    """Struktura pliku active_stt_backend.json przechowującego ID aktywnej instancji."""

    active_id: str = Field(description="ID aktualnie wybranego backendu STT")
