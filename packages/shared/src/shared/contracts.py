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


# ==========================================================================
# KONTRAKTY DLA CZATU I PAMIĘCI SESJI (AGENT OS CHAT & SESSION CONTRACTS)
# ==========================================================================


class ChatMessageDTO(BaseModel):
    """Pojedyncza wiadomość w historii konwersacji."""

    role: str = Field(..., description="Rola nadawcy: user, assistant, system")
    content: str = Field(..., description="Treść wiadomości tekstowej")
    timestamp: float = Field(..., description="Stempel czasowy wysłania wiadomości (Unix timestamp)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Dodatkowe metadane wiadomości")


class SendChatMessageRequest(BaseModel):
    """Żądanie wysłania nowej wiadomości do Agenta."""

    session_id: str = Field(default="default", description="Identyfikator sesji rozmowy w backendzie")
    message: str = Field(..., description="Treść nowej wiadomości od użytkownika/satelity")
    system_prompt: str | None = Field(default=None, description="Opcjonalny customowy system prompt")


class ChatResponseDTO(BaseModel):
    """Odpowiedź serwera po przetworzeniu wiadomości przez Agenta."""

    session_id: str = Field(..., description="Identyfikator sesji")
    message: ChatMessageDTO = Field(..., description="Wygenerowana wiadomość agenta")
    model: str | None = Field(default=None, description="Nazwa wywołanego modelu LLM")


class ChatSessionSummaryDTO(BaseModel):
    """Podsumowanie sesji dla listy sesji w interfejsie."""

    session_id: str = Field(..., description="Unikalny identyfikator techniczny sesji (np. session_a1b2c3d4)")
    title: str = Field(..., description="Wyświetlana nazwa/tytuł sesji")
    created_at: float = Field(..., description="Czas utworzenia sesji")
    updated_at: float = Field(..., description="Czas ostatniej aktywności")
    message_count: int = Field(..., description="Liczba wiadomości w sesji")


class ChatSessionHistoryResponse(BaseModel):
    """Odpowiedź z pełną historią i metadanymi konkretnej sesji konwersacji."""

    session_id: str = Field(..., description="Identyfikator techniczny sesji")
    title: str = Field(default="Nowa konwersacja", description="Wyświetlana nazwa sesji")
    messages: list[ChatMessageDTO] = Field(default_factory=list, description="Lista wiadomości w sesji")
    created_at: float = Field(..., description="Czas utworzenia sesji")
    updated_at: float = Field(..., description="Czas ostatniej aktywności sesji")


class ChatSessionListResponse(BaseModel):
    """Odpowiedź zawierająca listę dostępnych sesji konwersacyjnych."""

    sessions: list[ChatSessionSummaryDTO] = Field(default_factory=list, description="Lista podsumowań sesji")


class CancelChatApiRequest(BaseModel):
    """Żądanie anulowania generowania odpowiedzi dla sesji."""

    session_id: str = Field(..., description="Identyfikator sesji do anulowania")


