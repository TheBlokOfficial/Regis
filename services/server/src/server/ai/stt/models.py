from enum import Enum

from pydantic import Field

from server.ai.provider_models import ProviderInstanceContent


class STTProviderType(str, Enum):
    """Typy wspieranych dostawców STT (UPPERCASE Enum, mirror `ai.llm.models.ProviderType`)."""

    GROQ = "GROQ"


class STTInstanceFileContent(ProviderInstanceContent):
    """Struktura zawartości pliku JSON instancji STT (bez duplikacji ID na dysku)."""

    type: STTProviderType = Field(description="Typ dostawcy STT")


class STTInstanceConfig(STTInstanceFileContent):
    """Struktura instancji w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator instancji uzyskany z nazwy pliku")
