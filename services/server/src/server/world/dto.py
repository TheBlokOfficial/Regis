"""DTO prywatne dla REST API konfiguracji silnika świata."""

from pydantic import BaseModel, Field

from server.world.models import ClientCapability


class HomeAssistantConfigDTO(BaseModel):
    """Konfiguracja singletona Home Assistant dla API (access_token maskowany na GET)."""

    base_url: str = Field(..., description="Adres serwera Home Assistant")
    access_token: str = Field(..., description="Token dostępu — zamaskowany do ostatnich 4 znaków")


class UpdateHomeAssistantConfigRequest(BaseModel):
    """Żądanie dla PUT /config."""

    base_url: str = Field(..., description="Adres serwera Home Assistant")
    access_token: str | None = Field(
        default=None, description="Długoterminowy token dostępu — pomiń, aby zachować obecny"
    )


class TestHAConnectionRequest(BaseModel):
    """Żądanie dla POST /config/test."""

    base_url: str = Field(...)
    access_token: str | None = Field(
        default=None, description="Pomiń, aby przetestować z obecnie zapisanym tokenem"
    )


class TestConnectionResponse(BaseModel):
    """Odpowiedź dla POST /config/test."""

    ok: bool = Field(...)
    message: str = Field(..., description="Czytelny dla użytkownika komunikat wyniku testu")


class HAGroupDTO(BaseModel):
    """Reprezentacja grupy urządzeń dla API."""

    id: str = Field(..., description="Unikalne ID grupy (np. grp_a1b2c3d4)")
    name: str = Field(..., description="Wyświetlana nazwa grupy")
    device_ids: list[str] = Field(default_factory=list, description="Lista entity_id urządzeń wchodzących w grupę")


class CreateHAGroupRequest(BaseModel):
    """Żądanie dla POST /groups."""

    name: str = Field(...)
    device_ids: list[str] = Field(default_factory=list)
    custom_id: str | None = Field(default=None)


class UpdateHAGroupRequest(BaseModel):
    """Żądanie dla PUT /groups/{id}."""

    name: str | None = Field(default=None)
    device_ids: list[str] | None = Field(default=None)


class CatalogEntryDTO(BaseModel):
    """Jeden wpis surowego katalogu HA (przed deklaracją) — do wyszukiwarki w UI."""

    entity_id: str = Field(..., description="Natywny entity_id Home Assistant")
    friendly_name: str = Field(..., description="Nazwa zwrócona przez Home Assistant")
    kind: str = Field(..., description="Kategoria/domena encji (np. light, switch, sensor)")
    ha_area: str | None = Field(default=None, description="Surowa podpowiedź HA Area — nigdy prawda o pokoju")


class DeclaredDeviceDTO(BaseModel):
    """Jeden wpis zadeklarowanej listy — to, co widzi agent."""

    entity_id: str = Field(..., description="Natywny entity_id Home Assistant")
    display_name: str | None = Field(..., description="Nazwa nadpisana przez użytkownika, jeśli ustawiona")
    effective_name: str = Field(..., description="Nazwa widoczna dla agenta (display_name albo friendly_name z HA)")
    kind: str = Field(..., description="Kategoria urządzenia (np. light, switch, sensor)")
    capabilities: list[str] = Field(default_factory=list, description="Wspierane nazwy narzędzi")
    room_id: str | None = Field(default=None, description="Jedyne źródło prawdy o przypisaniu do pokoju")
    room_name: str | None = Field(default=None, description="Nazwa pokoju rozwiązana z room_id, do renderu w UI")


class AddDeclaredDeviceRequest(BaseModel):
    """Żądanie dla POST /declared."""

    entity_id: str = Field(...)
    display_name: str | None = Field(default=None)
    room_id: str | None = Field(default=None)


class UpdateDeclaredDeviceRequest(BaseModel):
    """Żądanie dla PUT /declared/{entity_id}."""

    display_name: str | None = Field(default=None)
    room_id: str | None = Field(default=None)


class RoomDTO(BaseModel):
    """Reprezentacja pokoju dla API."""

    id: str = Field(..., description="Unikalne ID pokoju (np. room_a1b2c3d4)")
    name: str = Field(..., description="Wyświetlana nazwa pokoju")


class CreateRoomRequest(BaseModel):
    """Żądanie dla POST /rooms."""

    name: str = Field(...)
    custom_id: str | None = Field(default=None)


class UpdateRoomRequest(BaseModel):
    """Żądanie dla PUT /rooms/{id}."""

    name: str = Field(...)


class SenderProfileDTO(BaseModel):
    """Nadawca dla API: jak się nazywa, gdzie stoi i co potrafi."""

    sender_id: str = Field(..., description="Opaque identyfikator nadawcy")
    display_name: str | None = Field(
        default=None, description="Przyjazna nazwa; pusta = UI pokazuje skrócony sender_id"
    )
    room_id: str | None = Field(default=None)
    room_name: str | None = Field(default=None, description="Nazwa pokoju rozwiązana z room_id, do renderu w UI")
    capabilities: list[ClientCapability] = Field(
        default_factory=list, description="Co klient potrafi (mic/speaker/text) — posortowane, stabilna kolejność"
    )


class PromptSectionDTO(BaseModel):
    """Jedna sekcja kontekstu tury. `warnings` liczone są po stronie serwera i
    zwracane też na GET (nie tylko po zapisie), żeby użytkownik widział problem
    od razu, a nie dopiero po rozmowie z agentem."""

    id: str
    label: str
    text: str
    condition: str
    condition_param: str | None = None
    negated: bool = False
    warnings: list[str] = Field(default_factory=list)


class ConditionSpecDTO(BaseModel):
    """Opis dostępnego warunku — UI buduje z tego listę rozwijaną, zamiast
    duplikować etykiety w JavaScripcie."""

    key: str
    label: str
    param_source: str | None = Field(default=None, description="'rooms' = warunek wymaga wyboru pokoju")


class PlaceholderSpecDTO(BaseModel):
    """Opis podstawienia. `guaranteed_by` pozwala UI pogrupować je na 'zawsze
    dostępne' i 'wymagają warunku'."""

    token: str
    label: str
    guaranteed_by: list[str] = Field(default_factory=list)


class PromptSectionsResponse(BaseModel):
    """Odpowiedź dla GET/PUT /api/v1/world/prompt-sections — sekcje wraz z
    metadanymi potrzebnymi do zbudowania edytora."""

    sections: list[PromptSectionDTO] = Field(default_factory=list)
    conditions: list[ConditionSpecDTO] = Field(default_factory=list)
    placeholders: list[PlaceholderSpecDTO] = Field(default_factory=list)


class UpdatePromptSectionsRequest(BaseModel):
    """Żądanie dla PUT /api/v1/world/prompt-sections — podmiana CAŁEJ listy.

    Kolejność elementów to kolejność w prompcie, więc przestawianie i usuwanie są
    naturalnie tą samą operacją co edycja; UI i tak trzyma całą listę.
    """

    sections: list[PromptSectionDTO] = Field(default_factory=list)


class PromptPreviewResponse(BaseModel):
    """Podgląd złożonego kontekstu tury dla wskazanego klienta."""

    turn_context: str = Field(..., description="Dokładnie ten tekst, który dostanie agent")
    sender_id: str | None = Field(default=None)


class RegisterSenderRequest(BaseModel):
    """Żądanie dla POST /senders (upsert — służy i rejestracji, i zmianie pokoju/nazwy)."""

    sender_id: str = Field(...)
    display_name: str | None = Field(
        default=None,
        description="Pominięte (None) zachowuje obecną nazwę; pusty string ją czyści",
    )
    room_id: str | None = Field(default=None)
    capabilities: list[ClientCapability] = Field(default_factory=list)
