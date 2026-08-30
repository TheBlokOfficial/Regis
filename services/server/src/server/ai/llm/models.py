from enum import Enum

from pydantic import Field

from server.ai.provider_models import ProviderInstanceContent


class ProviderType(str, Enum):
    """Typy wspieranych dostawców modeli LLM (UPPERCASE Enum)."""

    OLLAMA = "OLLAMA"
    OPENROUTER = "OPENROUTER"
    GROQ = "GROQ"


class BackendFileContent(ProviderInstanceContent):
    """Struktura zawartości pliku JSON instancji backendu (bez duplikacji ID na dysku)."""

    type: ProviderType = Field(description="Typ dostawcy modeli LLM")


class BackendInstanceConfig(BackendFileContent):
    """Struktura instancji w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator instancji uzyskany z nazwy pliku")
