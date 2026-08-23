from typing import Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Odpowiedź dla punktu końcowego GET /api/v1/health."""

    system: str = Field(default="Regis Agent OS", description="Nazwa systemu")
    gateway_status: str = Field(default="online", description="Status bramki sieciowej")
    agent_engine_status: str = Field(default="ready", description="Status silnika agenta")
    shared_version: str = Field(..., description="Wersja pakietu shared")


class LLMProviderDTO(BaseModel):
    """Reprezentacja instancji dostawcy LLM dla API."""

    id: str = Field(..., description="Unikalne ID instancji backendu (np. bk_ollama_local)")
    type: str = Field(..., description="Typ dostawcy (OLLAMA, OPENROUTER)")
    name: str = Field(..., description="Wyświetlana nazwa")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje konfiguracyjne")
    is_active: bool = Field(default=False, description="Czy ten dostawca jest obecnie aktywny")


class LLMProviderListResponse(BaseModel):
    """Odpowiedź dla GET /api/v1/llm/providers."""

    providers: list[LLMProviderDTO] = Field(default_factory=list, description="Lista dostępnych dostawców LLM")
    active_id: str = Field(..., description="ID obecnie aktywnego dostawcy")


class SelectLLMProviderRequest(BaseModel):
    """Żądanie dla PUT /api/v1/llm/providers/active."""

    provider_id: str = Field(..., description="ID dostawcy LLM do aktywacji")


class CreateLLMProviderRequest(BaseModel):
    """Żądanie dla POST /api/v1/llm/providers."""

    type: str = Field(..., description="Typ dostawcy (OLLAMA, OPENROUTER)")
    name: str = Field(..., description="Wyświetlana nazwa")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje konfiguracyjne")
    custom_id: str | None = Field(default=None, description="Opcjonalne własne ID")


class UpdateLLMProviderRequest(BaseModel):
    """Żądanie dla PUT /api/v1/llm/providers/{id} — edycja istniejącego presetu.

    Typ jest niezmienny (zmiana unieważniłaby wszystkie opcje), więc go tu nie ma.
    Pole sekretne (`api_key`) pominięte w `options` **zachowuje** obecną wartość —
    frontend nigdy nie zna jej w jawnej postaci (GET maskuje), więc nie mógłby jej
    odesłać z powrotem; ten sam wzorzec co token Home Assistant.
    """

    name: str | None = Field(default=None, description="Nowa nazwa presetu; pominięta zachowuje obecną")
    options: dict[str, Any] = Field(default_factory=dict, description="Opcje do nadpisania")


# ==========================================================================
# GENERYCZNA SPECYFIKACJA OPCJI DOSTAWCÓW LLM (CLEAN SOLID CONTRACTS)
# ==========================================================================


class ProviderOptionChoice(BaseModel):
    """Jedna dopuszczalna wartość pola typu `enum` (np. reasoning_effort: low/medium/high)."""

    value: str = Field(..., description="Wartość zapisywana w options")
    label: str = Field(..., description="Etykieta w interfejsie")


class ProviderOptionSpec(BaseModel):
    """Specyfikacja pojedynczego pola opcji konfiguracyjnej dostawcy LLM."""

    name: str = Field(..., description="Klucz pola w dict options (np. model, base_url, api_key)")
    label: str = Field(..., description="Etykieta wyświetlana w interfejsie")
    type: str = Field(default="string", description="Typ pola (string, password, number, enum, bool)")
    required: bool = Field(default=True, description="Czy pole jest wymagane")
    default_value: str | None = Field(default=None, description="Domyślna wartość")
    placeholder: str | None = Field(default=None, description="Tekst zastępczy (placeholder)")
    choices: list[ProviderOptionChoice] = Field(
        default_factory=list, description="Dopuszczalne wartości — wyłącznie dla type='enum'"
    )
    hint: str | None = Field(
        default=None, description="Jednozdaniowe wyjaśnienie pod polem — po co ten parametr istnieje"
    )


class ProviderTypeSpecDTO(BaseModel):
    """Specyfikacja typu dostawcy LLM zawierająca zestaw jego wymaganych opcji.

    `options_schema` to pola NIEZALEŻNE od wybranego modelu (klucz API, adres serwera).
    Parametry generacji są per model i przychodzą osobno, z `GET .../providers/{id}/models`
    — bo `reasoning_effort` istnieje dla gpt-oss, a nie istnieje dla llamy, i żadna
    wspólna lista pól nie opisze obu naraz.
    """

    type: str = Field(..., description="Identyfikator typu (np. OLLAMA, OPENROUTER dla LLM, HOME_ASSISTANT dla integracji)")
    label: str = Field(..., description="Wyświetlana nazwa typu")
    options_schema: list[ProviderOptionSpec] = Field(
        default_factory=list, description="Pola niezależne od modelu (klucz API, base_url)"
    )
    supports_model_discovery: bool = Field(
        default=False, description="Czy `GET .../providers/{id}/models` zwróci dla tego typu realną listę"
    )


class ModelSpecDTO(BaseModel):
    """Jeden model dostawcy wraz z formularzem parametrów, które akurat ON rozumie."""

    id: str = Field(..., description="Identyfikator modelu wysyłany do API dostawcy")
    label: str = Field(..., description="Nazwa w interfejsie")
    options_schema: list[ProviderOptionSpec] = Field(
        default_factory=list, description="Parametry generacji wspierane przez ten model"
    )


class ProviderModelsResponse(BaseModel):
    """Odpowiedź dla GET /api/v1/llm/providers/{id}/models.

    `detail` niesie powód pustej listy (brak klucza, padnięty serwer Ollamy) — UI pokazuje
    go zamiast udawać, że dostawca po prostu nie ma modeli.
    """

    models: list[ModelSpecDTO] = Field(default_factory=list)
    detail: str | None = Field(default=None)
    fallback_options_schema: list[ProviderOptionSpec] = Field(
        default_factory=list,
        description="Formularz dla modelu wpisanego ręcznie, spoza listy (zawsze wolno)",
    )


class ProviderMetadataResponse(BaseModel):
    """Odpowiedź dla GET /api/v1/llm/providers/schemas zawierająca schematy opcji."""

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

    session_id: str = Field(default="session_default", description="Identyfikator sesji rozmowy w backendzie")
    message: str = Field(..., description="Treść nowej wiadomości od użytkownika/satelity")
    sender_id: str | None = Field(
        default=None, description="Opaque identyfikator nadawcy (np. satelity) — nieinterpretowany przez kernel"
    )


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
    is_generating: bool = Field(default=False, description="Czy w sesji obecnie generowana jest odpowiedź w tle")


class ChatSessionHistoryResponse(BaseModel):
    """Odpowiedź z pełną historią i metadanymi konkretnej sesji konwersacji."""

    session_id: str = Field(..., description="Identyfikator techniczny sesji")
    title: str = Field(default="Nowa konwersacja", description="Wyświetlana nazwa sesji")
    messages: list[ChatMessageDTO] = Field(default_factory=list, description="Lista wiadomości w sesji")
    created_at: float = Field(..., description="Czas utworzenia sesji")
    updated_at: float = Field(..., description="Czas ostatniej aktywności sesji")
    is_generating: bool = Field(default=False, description="Czy w sesji obecnie generowana jest odpowiedź w tle")


class ChatSessionListResponse(BaseModel):
    """Odpowiedź zawierająca listę dostępnych sesji konwersacyjnych."""

    sessions: list[ChatSessionSummaryDTO] = Field(default_factory=list, description="Lista podsumowań sesji")


class CancelChatApiRequest(BaseModel):
    """Żądanie anulowania generowania odpowiedzi dla sesji."""

    session_id: str = Field(..., description="Identyfikator sesji do anulowania")


# ==========================================================================
# KONTRAKTY DLA MAGAZYNU PROMPTÓW SYSTEMOWYCH (PROMPT STORE CONTRACTS)
# ==========================================================================


class PromptDTO(BaseModel):
    """Reprezentacja instancji promptu systemowego dla API."""

    id: str = Field(..., description="Unikalny identyfikator promptu (np. prompt_default)")
    name: str = Field(..., description="Wyświetlana nazwa promptu")
    content: str = Field(..., description="Treść instrukcji systemowej")
    description: str | None = Field(default=None, description="Opcjonalny opis przeznaczenia promptu")
    is_active: bool = Field(default=False, description="Czy ten prompt jest obecnie aktywny")


class PromptListResponse(BaseModel):
    """Odpowiedź dla GET /api/v1/agent/prompts."""

    prompts: list[PromptDTO] = Field(default_factory=list, description="Lista dostępnych promptów")
    active_id: str = Field(..., description="ID aktualnie aktywnego promptu")


class CreatePromptRequest(BaseModel):
    """Żądanie dla POST /api/v1/agent/prompts."""

    name: str = Field(..., description="Wyświetlana nazwa promptu")
    content: str = Field(..., description="Treść instrukcji systemowej")
    description: str | None = Field(default=None, description="Opcjonalny opis")
    custom_id: str | None = Field(default=None, description="Opcjonalne własne ID (np. prompt_coding)")
    set_active: bool = Field(default=False, description="Czy od razu aktywować ten prompt")


class UpdatePromptRequest(BaseModel):
    """Żądanie dla PUT /api/v1/world/prompts/{id}."""

    name: str | None = Field(default=None, description="Nowa wyświetlana nazwa")
    content: str | None = Field(default=None, description="Nowa treść instrukcji")
    description: str | None = Field(default=None, description="Nowy opis")


class AgentDefaultPromptDTO(BaseModel):
    """Fallbackowy prompt systemowy kernela — GET/PUT /api/v1/agent/prompt.
    Używany wyłącznie gdy żaden silnik świata nie dostarcza własnego promptu."""

    content: str = Field(..., description="Treść fallbackowej instrukcji systemowej agenta")


# ==========================================================================
# KONTRAKTY DLA REJESTRU ROZSZERZEŃ (EXTENSIONS REGISTRY CONTRACTS)
# ==========================================================================
#
# Generyczny kształt „lista rozszerzeń" — jedyna treść współdzielona między
# rozszerzeniami. Prywatne słownictwo poszczególnych rozszerzeń (np. Home
# Assistant — połączenia, katalog, grupy) żyje lokalnie w ich własnych
# pakietach (`server/extensions/home_assistant/dto.py`), nie tutaj.


