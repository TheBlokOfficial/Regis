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
    """Nadawca dla API: gdzie stoi i co potrafi."""

    sender_id: str = Field(..., description="Opaque identyfikator nadawcy")
    room_id: str | None = Field(default=None)
    room_name: str | None = Field(default=None, description="Nazwa pokoju rozwiązana z room_id, do renderu w UI")
    capabilities: list[ClientCapability] = Field(
        default_factory=list, description="Co klient potrafi (mic/speaker/text) — posortowane, stabilna kolejność"
    )


class PromptSectionDTO(BaseModel):
    """Jedna sekcja kontekstu tury wraz z metadanymi potrzebnymi UI.

    `default` jest zwracany celowo, mimo że to stała po stronie serwera — dzięki
    temu przycisk "Przywróć domyślne" i podgląd wartości bazowej działają bez
    duplikowania tych samych tekstów w JavaScripcie (jedno źródło prawdy).
    """

    key: str = Field(..., description="Identyfikator sekcji, np. delivery_voice")
    label: str = Field(..., description="Nazwa widoczna w UI")
    condition: str = Field(..., description="Kiedy sekcja trafia do promptu — opis dla użytkownika")
    placeholders: list[str] = Field(default_factory=list, description="Dozwolone podstawienia, np. {czas}")
    default: str = Field(..., description="Wartość domyślna (tekst wbudowany w serwer)")
    value: str = Field(..., description="Wartość obowiązująca — nadpisanie albo domyślna")
    is_overridden: bool = Field(..., description="Czy użytkownik nadpisał wartość domyślną")


class PromptSectionsResponse(BaseModel):
    """Odpowiedź dla GET /api/v1/world/prompt-sections."""

    sections: list[PromptSectionDTO] = Field(default_factory=list)


class UpdatePromptSectionsRequest(BaseModel):
    """Żądanie dla PUT /api/v1/world/prompt-sections.

    Klucz nieobecny w `sections` = bez zmian. Wartość `null` = przywróć domyślną.
    Pusty string = wycisz sekcję (świadomie różne od przywrócenia domyślnej).
    """

    sections: dict[str, str | None] = Field(default_factory=dict)


class RegisterSenderRequest(BaseModel):
    """Żądanie dla POST /senders (upsert — służy i rejestracji, i zmianie pokoju)."""

    sender_id: str = Field(...)
    room_id: str | None = Field(default=None)
    capabilities: list[ClientCapability] = Field(default_factory=list)
