"""DTO prywatne dla REST API rozszerzenia Home Assistant.

Prywatne słownictwo tego rozszerzenia — nie żyje w `packages/shared`, w
przeciwieństwie do `ProviderOptionSpec`/`ProviderTypeSpecDTO` (nadal
schema-driven dla dostawców LLM, gdzie realna wymienność backendu istnieje).
"""

from pydantic import BaseModel, Field


class HAConnectionDTO(BaseModel):
    """Reprezentacja połączenia Home Assistant dla API (access_token maskowany)."""

    id: str = Field(..., description="Unikalne ID połączenia (np. con_a1b2c3d4)")
    name: str = Field(..., description="Wyświetlana nazwa")
    base_url: str = Field(..., description="Adres serwera Home Assistant")
    access_token: str = Field(..., description="Token dostępu — zamaskowany do ostatnich 4 znaków")
    enabled: bool = Field(..., description="Czy połączenie aktywnie dostarcza urządzenia agentowi")


class CreateHAConnectionRequest(BaseModel):
    """Żądanie dla POST /connections."""

    name: str = Field(..., description="Wyświetlana nazwa")
    base_url: str = Field(..., description="Adres serwera Home Assistant")
    access_token: str = Field(..., description="Długoterminowy token dostępu")
    enabled: bool = Field(default=True, description="Czy połączenie ma być od razu włączone")
    custom_id: str | None = Field(default=None, description="Opcjonalne własne ID")


class UpdateHAConnectionRequest(BaseModel):
    """Żądanie dla PUT /connections/{id}."""

    name: str | None = Field(default=None)
    base_url: str | None = Field(default=None)
    access_token: str | None = Field(default=None)
    enabled: bool | None = Field(default=None)


class HAGroupDTO(BaseModel):
    """Reprezentacja grupy urządzeń dla API."""

    id: str = Field(..., description="Unikalne ID grupy (np. grp_a1b2c3d4)")
    name: str = Field(..., description="Wyświetlana nazwa grupy")
    device_ids: list[str] = Field(default_factory=list, description="Lista namespaced ref urządzeń wchodzących w grupę")


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
    """Jeden wpis katalogu urządzeń danego połączenia (przed/po deklaracji widoczności)."""

    ref: str = Field(..., description="Namespaced ref (connection_id:native_id) — ten sam używany w device_ids grupy")
    label: str = Field(..., description="Nazwa po zastosowaniu ewentualnej deklaracji display_name")
    kind: str = Field(..., description="Kategoria urządzenia (np. light, switch, sensor)")
    capabilities: list[str] = Field(default_factory=list, description="Wspierane nazwy narzędzi")
    enabled: bool = Field(..., description="Czy urządzenie jest widoczne dla agenta wg deklaracji")


class CatalogEntryUpdate(BaseModel):
    """Jedna pozycja w żądaniu zbiorczego zapisu katalogu."""

    ref: str = Field(..., description="Namespaced ref urządzenia")
    enabled: bool = Field(default=True)
    display_name: str | None = Field(default=None)


class UpdateCatalogRequest(BaseModel):
    """Żądanie dla PUT /connections/{id}/catalog — zbiorczy zapis deklaracji."""

    entries: list[CatalogEntryUpdate] = Field(default_factory=list)
