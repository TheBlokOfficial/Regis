"""Model domenowy i konfiguracyjny silnika świata.

`Device`/`DeviceGroup`/`Room`/`SenderProfile` są pojęciami należącymi
wyłącznie do tego silnika, nie do kernela. World nie zna konkretnego typu
urządzenia ("satelita ESP32", "karta przeglądarki") ani transportu, którym
klient przyszedł — zna opaque `sender_id`, jego `Room` i jego `capabilities`
(co ta rzecz potrafi: mikrofon/głośnik/tekst).

**Rewizja wcześniejszej decyzji**: modalność (głos/tekst) była tu dawniej
świadomie nieobecna i przenoszona przez kernel jako efemeryczny parametr
wywołania `WorldEngine.build(voice_mode=...)`. Okazało się to niespójne z tym,
jak system realnie działa: flaga opisywała wejście, a decydowała o framingu
wyjścia, którego cel potrafi się zmienić w połowie tury (`speak_in_room`).
`ClientCapability` modeluje to poprawnie — jako trwały fakt o rzeczy w świecie,
symetrycznie do `Device.capabilities` — i pozwala kernelowi przestać cokolwiek
o kanale wiedzieć (patrz `agent/context_provider.py`).

`Room` jest pełnoprawnym, niezależnym od Home Assistant bytem World — nie
surowym `area_id` HA. HA renamując/usuwając swoją Area nie może po cichu
zepsuć mapowania nadawcy: `Device.area` zostaje wyłącznie **podpowiedzią**
(widoczną w surowym katalogu HA, do ręcznego przypisania w UI), nigdy
prawdą. Jedyne źródło prawdy o przypisaniu do pokoju to
`DeclaredDeviceEntry.room_id` (urządzenia) i `SenderProfile.room_id`
(nadawcy).
"""

from dataclasses import dataclass, field
from enum import Enum

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


class ClientCapability(str, Enum):
    """Co dany klient fizycznie potrafi — mirror `Device.capabilities` (ta sama
    idea: trwały fakt o rzeczy w świecie, nie o bieżącym wywołaniu).

    Świadomie NIE ma tu pola `kind` ("satelita"/"przeglądarka") — typ klienta jest
    w całości wyprowadzalny z tego zbioru (ikona i etykieta w UI, framing promptu),
    a drugie, redundantne źródło prawdy prędzej czy później rozjechałoby się z tym.
    """

    MIC = "mic"
    """Klient potrafi nagrywać mowę — wiadomości od niego przychodzą głosem."""

    SPEAKER = "speaker"
    """Klient potrafi odtworzyć audio — odpowiedź do niego zostanie zsyntetyzowana (TTS)."""

    TEXT = "text"
    """Klient wyświetla tekst — odpowiedź trafia do historii czatu, nie do syntezy."""


class SenderProfile(BaseModel):
    """Jeden opaque `sender_id`: jak się nazywa (`display_name`), gdzie stoi (`room_id`)
    i co potrafi (`capabilities`).

    `display_name` to czysto ludzka etykieta — dokładny mirror
    `DeclaredDeviceEntry.display_name`, bo klient stojący w pokoju jest takim samym bytem
    World co żarówka. Adresowanie nadal idzie po opaque `sender_id`/pokoju, nigdy po
    nazwie (patrz `docs/manifest.md`, "Adresowanie po natywnym ID, nie po nazwie").

    `room_id` to odsyłacz do `Room` (katalog World) — etykieta pokoju do promptu
    liczona jest w `WorldEngine.build()` z katalogu, nigdy przechowywana tutaj
    (eliminuje ryzyko rozjazdu, ten sam wzorzec co usunięcie dawnego pola `channel`).

    `capabilities` zastąpiło dawną, przenoszoną przez kernel flagę `voice_mode`:
    modalność wejścia (`MIC` → przyszło głosem) i wyjścia (`SPEAKER` → odpowiedź
    zostanie zsyntetyzowana) są **trwałym faktem o kliencie**, a nie parametrem
    pojedynczego wywołania, więc World wyprowadza je sobie sam. Dzięki temu
    `WorldInterface.build()` potrzebuje wyłącznie `sender_id`, a kernel nie musi
    przenosić przez siebie wiedzy o kanale (patrz `agent/context_provider.py`).
    """

    display_name: str | None = Field(
        default=None,
        description="Przyjazna nazwa klienta — mirror DeclaredDeviceEntry.display_name; pusta = pokaż skrócone ID",
    )
    room_id: str | None = Field(default=None, description="Odsyłacz do Room — jedyne źródło prawdy o lokalizacji nadawcy")
    capabilities: frozenset[ClientCapability] = Field(
        default_factory=frozenset, description="Co klient potrafi — mic/speaker/text"
    )


class SenderProfilesFileContent(BaseModel):
    """Zawartość pliku przypisań nadawców do pokoi. Klucz `entries` to opaque `sender_id`."""

    entries: dict[str, SenderProfile] = Field(default_factory=dict)
