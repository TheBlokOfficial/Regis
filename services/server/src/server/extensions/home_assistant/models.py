"""Model domenowy i konfiguracyjny rozszerzenia Home Assistant.

`Device`/`DeviceGroup` są pojęciami należącymi wyłącznie do tego rozszerzenia,
nie do kernela — inne rozszerzenie miałoby własną nazwę i pola dla swojej
wersji generycznej `EntitySpec` z `agent/plugin_contract.py`.
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
        (pusty `frozenset()` = pełne, niepodzielone wsparcie narzędzia — ten
        sam kształt co `EntityCapability` z Kontraktu, tylko jako słownik).
    :param area: Opcjonalny, luźny tag lokalizacji (bez żadnego rejestru/FK — czysto informacyjny).
    """

    id: str
    name: str
    kind: str
    capabilities: dict[str, frozenset[str]] = field(default_factory=dict)
    area: str | None = None


@dataclass
class DeviceGroup:
    """Nazwana, dowolna kolekcja urządzeń — niezależna od ich lokalizacji."""

    id: str
    name: str
    device_ids: list[str]


class HomeAssistantConfig(BaseModel):
    """Konfiguracja jedynej, globalnej instancji Home Assistant (singleton).

    Puste pola oznaczają rozszerzenie nieskonfigurowane.
    """

    base_url: str = Field(default="", description="Adres serwera Home Assistant")
    access_token: str = Field(default="", description="Długoterminowy token dostępu (Long-Lived Access Token)")


class DeviceGroupFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji grupy urządzeń.

    Grupy są prywatną, rozszerzenie-wide konfiguracją (nie per-połączenie).
    """

    name: str = Field(description="Wyświetlana nazwa grupy")
    device_ids: list[str] = Field(default_factory=list, description="Lista entity_id urządzeń wchodzących w grupę")


class DeviceGroupInstanceConfig(DeviceGroupFileContent):
    """Struktura instancji grupy w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator grupy uzyskany z nazwy pliku")


class DeclaredDeviceEntry(BaseModel):
    """Deklaracja jednego urządzenia widocznego dla agenta."""

    display_name: str | None = Field(default=None, description="Nadpisuje nazwę zwróconą przez client.list_devices()")


class DeclaredDevicesFileContent(BaseModel):
    """Zawartość pliku zadeklarowanych urządzeń — jedyne źródło prawdy o tym, co widzi agent.

    Klucz `entries` to natywny `entity_id`. Model opt-in: brak wpisu oznacza
    niewidoczność, niezależnie od tego, czy encja istnieje po stronie HA.
    """

    entries: dict[str, DeclaredDeviceEntry] = Field(default_factory=dict)
