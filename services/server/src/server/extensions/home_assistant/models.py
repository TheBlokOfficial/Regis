"""Model domenowy i konfiguracyjny rozszerzenia Home Assistant.

`Device`/`DeviceGroup` są pojęciami należącymi wyłącznie do tego rozszerzenia,
nie do kernela — inne rozszerzenie miałoby własną nazwę i pola dla swojej
wersji generycznej `EntitySpec` z `agent/plugin_contract.py`.
"""

from dataclasses import dataclass, field

from pydantic import BaseModel, Field


@dataclass
class Device:
    """Pojedyncze urządzenie dostarczone przez połączenie Home Assistant.

    :param id: Namespaced identyfikator wewnętrzny rozszerzenia (np.
        'con_ha_main:light.bathroom') — nigdy nie opuszcza rozszerzenia w tej
        postaci, Gateway nadaje mu opaque ID.
    :param connection_id: ID połączenia HA, które dostarczyło to urządzenie.
    :param name: Przyjazna nazwa widoczna dla agenta/użytkownika.
    :param kind: Kategoria urządzenia (np. 'light', 'switch', 'climate', 'sensor').
    :param capabilities: Zbiór wspieranych nazw narzędzi (np. 'turn_on', 'turn_off', 'get_state').
    :param area: Opcjonalny, luźny tag lokalizacji (bez żadnego rejestru/FK — czysto informacyjny).
    """

    id: str
    connection_id: str
    name: str
    kind: str
    capabilities: set[str] = field(default_factory=set)
    area: str | None = None


@dataclass
class DeviceGroup:
    """Nazwana, dowolna kolekcja urządzeń — niezależna od ich lokalizacji.

    Urządzenia w grupie mogą pochodzić z różnych połączeń HA — rozwiązanie
    grup jest w pełni wewnętrzną sprawą rozszerzenia.
    """

    id: str
    name: str
    device_ids: list[str]


class HAConnectionFileContent(BaseModel):
    """Struktura zawartości pliku JSON połączenia Home Assistant (bez duplikacji ID na dysku)."""

    name: str = Field(description="Wyświetlana nazwa połączenia")
    base_url: str = Field(description="Adres serwera Home Assistant")
    access_token: str = Field(description="Długoterminowy token dostępu (Long-Lived Access Token)")
    enabled: bool = Field(default=True, description="Czy połączenie aktywnie dostarcza urządzenia agentowi")


class HAConnectionConfig(HAConnectionFileContent):
    """Struktura połączenia w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator połączenia uzyskany z nazwy pliku")


class DeviceGroupFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji grupy urządzeń.

    Grupy są prywatną, rozszerzenie-wide konfiguracją (nie per-połączenie).
    """

    name: str = Field(description="Wyświetlana nazwa grupy")
    device_ids: list[str] = Field(default_factory=list, description="Lista namespaced ID urządzeń wchodzących w grupę")


class DeviceGroupInstanceConfig(DeviceGroupFileContent):
    """Struktura instancji grupy w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator grupy uzyskany z nazwy pliku")


class DeviceDeclarationEntry(BaseModel):
    """Deklaracja widoczności/nazwy jednego urządzenia w katalogu połączenia."""

    enabled: bool = Field(default=True, description="Czy urządzenie ma być widoczne dla agenta")
    display_name: str | None = Field(default=None, description="Nadpisuje nazwę zwróconą przez client.list_devices()")


class DeviceDeclarationFileContent(BaseModel):
    """Zawartość pliku deklaracji katalogu jednego połączenia.

    Klucz `entries` to natywny ID urządzenia (bez namespace połączenia). Brak
    pliku (lub brak wpisu dla danego ID) oznacza pełną widoczność — świeże
    połączenie wystawia agentowi wszystko, zanim ktoś cokolwiek zadeklaruje.
    """

    entries: dict[str, DeviceDeclarationEntry] = Field(default_factory=dict)
