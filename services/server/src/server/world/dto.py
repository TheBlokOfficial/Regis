"""DTO prywatne dla REST API konfiguracji silnika świata."""

from pydantic import BaseModel, Field


class HomeAssistantConfigDTO(BaseModel):
    """Konfiguracja singletona Home Assistant dla API (access_token maskowany na GET)."""

    base_url: str = Field(..., description="Adres serwera Home Assistant")
    access_token: str = Field(..., description="Token dostępu — zamaskowany do ostatnich 4 znaków")


class UpdateHomeAssistantConfigRequest(BaseModel):
    """Żądanie dla PUT /config."""

    base_url: str = Field(..., description="Adres serwera Home Assistant")
    access_token: str = Field(..., description="Długoterminowy token dostępu")


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
    """Przypisanie nadawcy do pokoju dla API."""

    sender_id: str = Field(..., description="Opaque identyfikator nadawcy")
    room_id: str | None = Field(default=None)
    room_name: str | None = Field(default=None, description="Nazwa pokoju rozwiązana z room_id, do renderu w UI")


class RegisterSenderRequest(BaseModel):
    """Żądanie dla POST /senders."""

    sender_id: str = Field(...)
    room_id: str | None = Field(default=None)
