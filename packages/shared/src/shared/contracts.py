from typing import Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Odpowiedź dla punktu końcowego GET /api/health."""

    system: str = Field(default="Regis Agent OS", description="Nazwa systemu")
    gateway_status: str = Field(default="online", description="Status bramki sieciowej")
    agent_engine_status: str = Field(default="ready", description="Status silnika agenta")
    shared_version: str = Field(..., description="Wersja pakietu shared")


class LLMProviderDTO(BaseModel):
    """Reprezentacja instancji dostawcy LLM dla API."""

    id: str = Field(..., description="Unikalne ID instancji backendu (np. bk_ollama_local)")
    type: str = Field(..., description="Typ dostawcy (OLLAMA, OPENROUTER, OPENAI)")
    name: str = Field(..., description="Wyświetlana nazwa")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje konfiguracyjne")
    is_active: bool = Field(default=False, description="Czy ten dostawca jest obecnie aktywny")


class LLMProviderListResponse(BaseModel):
    """Odpowiedź dla GET /api/llm/providers."""

    providers: list[LLMProviderDTO] = Field(default_factory=list, description="Lista dostępnych dostawców LLM")
    active_id: str = Field(..., description="ID obecnie aktywnego dostawcy")


class SelectLLMProviderRequest(BaseModel):
    """Żądanie dla PUT /api/llm/providers/active."""

    provider_id: str = Field(..., description="ID dostawcy LLM do aktywacji")


class CreateLLMProviderRequest(BaseModel):
    """Żądanie dla POST /api/llm/providers."""

    type: str = Field(..., description="Typ dostawcy (OLLAMA, OPENROUTER, OPENAI)")
    name: str = Field(..., description="Wyświetlana nazwa")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje konfiguracyjne")
    custom_id: str | None = Field(default=None, description="Opcjonalne własne ID")


# ==========================================================================
# GENERYCZNA SPECYFIKACJA OPCJI DOSTAWCÓW LLM (CLEAN SOLID CONTRACTS)
# ==========================================================================


class ProviderOptionSpec(BaseModel):
    """Specyfikacja pojedynczego pola opcji konfiguracyjnej dostawcy LLM."""

    name: str = Field(..., description="Klucz pola w dict options (np. model, base_url, api_key)")
    label: str = Field(..., description="Etykieta wyświetlana w interfejsie")
    type: str = Field(default="string", description="Typ pola HTML (string, password)")
    required: bool = Field(default=True, description="Czy pole jest wymagane")
    default_value: str | None = Field(default=None, description="Domyślna wartość")
    placeholder: str | None = Field(default=None, description="Tekst zastępczy (placeholder)")


class ProviderTypeSpecDTO(BaseModel):
    """Specyfikacja typu dostawcy LLM zawierająca zestaw jego wymaganych opcji."""

    type: str = Field(..., description="Identyfikator typu (OLLAMA, OPENROUTER, OPENAI)")
    label: str = Field(..., description="Wyświetlana nazwa typu")
    options_schema: list[ProviderOptionSpec] = Field(
        default_factory=list, description="Lista specyfikacji pól konfiguracyjnych"
    )


class ProviderMetadataResponse(BaseModel):
    """Odpowiedź dla GET /api/llm/providers/schemas zawierająca schematy opcji."""

    provider_types: list[ProviderTypeSpecDTO] = Field(
        default_factory=list, description="Lista wspieranych typów z ich schematami opcji"
    )
