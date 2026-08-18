"""Model domenowy i konfiguracyjny silnika świata.

`Device`/`DeviceGroup`/`Room`/`SenderProfile` są pojęciami należącymi
wyłącznie do tego silnika, nie do kernela. World nie ma pojęcia "satelity" —
zna wyłącznie opaque `sender_id` i mapuje go na swój wewnętrzny `Room`. Kanał
komunikacji (głos/tekst) i tożsamość fizycznego urządzenia (satelita ESP32,
Web UI, ...) to wiedza `server.voice`, nigdy World — World dostaje tę
informację jako efemeryczny parametr wywołania
(`WorldEngine.build(voice_mode=...)`), nigdy jako trwały stan.

`Room` jest pełnoprawnym, niezależnym od Home Assistant bytem World — nie
surowym `area_id` HA. HA renamując/usuwając swoją Area nie może po cichu
zepsuć mapowania nadawcy: `Device.area` zostaje wyłącznie **podpowiedzią**
(widoczną w surowym katalogu HA, do ręcznego przypisania w UI albo
jednorazowego importu, `WorldEngine.import_rooms_from_ha()`), nigdy prawdą.
Jedyne źródło prawdy o przypisaniu do pokoju to `DeclaredDeviceEntry.room_id`
(urządzenia) i `SenderProfile.room_id` (nadawcy).
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


@dataclass
class Device:
    """Pojedyncze urządzenie (encja Home Assistant) widoczne dla agenta.

    :param id: Natywny `entity_id` Home Assistant (np. 'light.bathroom') —
        jedna instancja HA (singleton), więc bez przestrzeni nazw połączenia.
    :param name: Przyjazna nazwa widoczna dla agenta/użytkownika.
    :param kind: Kategoria urządzenia (np. 'light', 'switch', 'climate', 'sensor').
    :param capabilities: Mapa nazwa narzędzia → granularne cechy w jej obrębie
        (pusty `frozenset()` = pełne, niepodzielone wsparcie narzędzia).
    :param area: Opcjonalny tag lokalizacji — natywny `area_id` z Home Assistant.
    """

    id: str
    name: str
    kind: str
    capabilities: dict[str, frozenset[str]] = field(default_factory=dict)
    area: str | None = None
    """Surowy `area_id` z Home Assistant — wyłącznie podpowiedź (import/UI), nigdy prawda o pokoju."""
    room_id: str | None = None
    """Jedyne źródło prawdy o przypisaniu do `Room` — kopiowane z `DeclaredDeviceEntry.room_id`."""


@dataclass
class DeviceGroup:
    """Nazwana, dowolna kolekcja urządzeń — niezależna od ich lokalizacji."""

    id: str
    name: str
    device_ids: list[str]


@dataclass
class Room:
    """Pokój — pełnoprawny, niezależny od Home Assistant byt World.

    Analogiczny do `DeviceGroup` (ten sam wzorzec CRUD/pliku JSON), ale
    o innym przeznaczeniu: segregacja przestrzenna urządzeń (`Device.room_id`)
    i lokalizacja nadawców (`SenderProfile.room_id`), nigdy dowolne grupowanie.
    """

    id: str
    name: str


class HomeAssistantConfig(BaseModel):
    """Konfiguracja jedynej, globalnej instancji Home Assistant (singleton).

    Puste pola oznaczają brak konfiguracji — silnik degraduje się łagodnie
    (encje/narzędzia HA po prostu nie są dostarczane), bez osobnego przełącznika.
    """

    base_url: str = Field(default="", description="Adres serwera Home Assistant")
    access_token: str = Field(default="", description="Długoterminowy token dostępu (Long-Lived Access Token)")


class DeviceGroupFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji grupy urządzeń."""

    name: str = Field(description="Wyświetlana nazwa grupy")
    device_ids: list[str] = Field(default_factory=list, description="Lista entity_id urządzeń wchodzących w grupę")


class DeviceGroupInstanceConfig(DeviceGroupFileContent):
    """Struktura instancji grupy w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator grupy uzyskany z nazwy pliku")


class RoomFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji pokoju."""

    name: str = Field(description="Wyświetlana nazwa pokoju")


class RoomInstanceConfig(RoomFileContent):
    """Struktura instancji pokoju w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator pokoju uzyskany z nazwy pliku")


class DeclaredDeviceEntry(BaseModel):
    """Deklaracja jednego urządzenia widocznego dla agenta."""

    display_name: str | None = Field(default=None, description="Nadpisuje nazwę zwróconą przez client.list_devices()")
    room_id: str | None = Field(default=None, description="Jedyne źródło prawdy o przypisaniu urządzenia do pokoju")


class DeclaredDevicesFileContent(BaseModel):
    """Zawartość pliku zadeklarowanych urządzeń — jedyne źródło prawdy o tym, co widzi agent.

    Klucz `entries` to natywny `entity_id`. Model opt-in: brak wpisu oznacza
    niewidoczność, niezależnie od tego, czy encja istnieje po stronie HA.
    """

    entries: dict[str, DeclaredDeviceEntry] = Field(default_factory=dict)


class SenderProfile(BaseModel):
    """Przypisanie jednego opaque `sender_id` do `Room` — jedyna wiedza World o nadawcy.

    Wyłącznie `room_id` (odsyłacz do `Room`, katalog World) — etykieta pokoju
    do promptu liczona jest w `WorldEngine.build()` z katalogu `Room`, nigdy
    przechowywana tutaj (eliminuje ryzyko rozjazdu, ten sam wzorzec co
    usunięcie dawnego pola `channel`). Zero wiedzy o kanale komunikacji ani
    o typie fizycznego urządzenia — to kompetencja `server.voice`.
    """

    room_id: str | None = Field(default=None, description="Odsyłacz do Room — jedyne źródło prawdy o lokalizacji nadawcy")


class SenderProfilesFileContent(BaseModel):
    """Zawartość pliku przypisań nadawców do pokoi. Klucz `entries` to opaque `sender_id`."""

    entries: dict[str, SenderProfile] = Field(default_factory=dict)
