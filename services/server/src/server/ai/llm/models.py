from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProviderType(str, Enum):
    """Typy wspieranych dostawców modeli LLM (UPPERCASE Enum)."""

    OLLAMA = "OLLAMA"
    OPENROUTER = "OPENROUTER"
    GROQ = "GROQ"


class BackendFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji backendu (bez duplikacji ID na dysku)."""

    type: ProviderType = Field(description="Typ dostawcy modeli LLM")
    name: str = Field(description="Wyświetlana nazwa instancji")
    options: dict[str, Any] = Field(default_factory=dict, description="Worek z opcjami specyficznymi dla dostawcy")


class BackendInstanceConfig(BackendFileContent):
    """Struktura instancji w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator instancji uzyskany z nazwy pliku")


class ActiveBackendConfig(BaseModel):
    """Struktura pliku active_backend.json przechowującego ID aktywnej instancji."""

    active_id: str = Field(description="ID aktualnie wybranego backendu")
