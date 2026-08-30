from enum import Enum

from pydantic import Field

from server.ai.provider_models import ProviderInstanceContent


class TTSProviderType(str, Enum):
    """Typy wspieranych dostawców TTS (UPPERCASE Enum, mirror `ai.llm.models.ProviderType`)."""

    ELEVENLABS = "ELEVENLABS"


class TTSInstanceFileContent(ProviderInstanceContent):
    """Struktura zawartości pliku JSON instancji TTS (bez duplikacji ID na dysku)."""

    type: TTSProviderType = Field(description="Typ dostawcy TTS")


class TTSInstanceConfig(TTSInstanceFileContent):
    """Struktura instancji w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator instancji uzyskany z nazwy pliku")
