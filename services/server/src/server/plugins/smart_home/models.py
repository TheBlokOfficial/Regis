"""Model domenowy i konfiguracyjny pluginu Smart Home.

`Device`/`DeviceGroup` są pojęciami należącymi do tego konkretnego pluginu,
nie do kernela (wizja, sekcja 5) — inny plugin miałby własną nazwę i pola
dla swojej wersji generycznej `EntitySpec` z `plugin_contract.py`.
"""

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


@dataclass
class Device:
    """Pojedyncze urządzenie dostarczone przez integrację (`DeviceIntegration`).

    :param id: Namespaced identyfikator wewnętrzny pluginu (np. 'int_ha_main:light.bathroom')
        — nigdy nie opuszcza pluginu w tej postaci, Gateway nadaje mu opaque ID.
    :param integration_id: ID instancji integracji, która dostarczyła to urządzenie.
    :param name: Przyjazna nazwa widoczna dla agenta/użytkownika.
    :param kind: Kategoria urządzenia (np. 'light', 'switch', 'climate', 'sensor').
    :param capabilities: Zbiór wspieranych nazw narzędzi (np. 'turn_on', 'turn_off', 'get_state').
    :param area: Opcjonalny, luźny tag lokalizacji (bez żadnego rejestru/FK — czysto informacyjny).
    """

    id: str
    integration_id: str
    name: str
    kind: str
    capabilities: set[str] = field(default_factory=set)
    area: str | None = None


@dataclass
class DeviceGroup:
    """Nazwana, dowolna kolekcja urządzeń — niezależna od ich lokalizacji.

    Urządzenia w grupie mogą pochodzić z różnych integracji tego samego
    pluginu — to właśnie dlatego rozwiązanie grup jest w pełni wewnętrzną
    sprawą pluginu (wizja, sekcja 4.4).
    """

    id: str
    name: str
    device_ids: list[str]


class IntegrationFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji integracji (bez duplikacji ID na dysku).

    `type` jest zwykłym stringiem, nie zamkniętym enumem — plugin nie zna z góry
    zbioru możliwych integracji, tylko te, które same się w nim zarejestrowały
    (`SmartHomePlugin.register_integration_type`). Nieznany typ jest wykrywany
    dopiero przy próbie utworzenia instancji, nie na poziomie schematu danych.
    """

    type: str = Field(description="Identyfikator zarejestrowanego typu integracji (nadany przez samą integrację)")
    name: str = Field(description="Wyświetlana nazwa instancji")
    options: dict[str, Any] = Field(default_factory=dict, description="Worek z opcjami specyficznymi dla integracji")
    enabled: bool = Field(default=True, description="Czy integracja aktywnie dostarcza urządzenia agentowi")


class IntegrationInstanceConfig(IntegrationFileContent):
    """Struktura instancji w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator instancji uzyskany z nazwy pliku")


class DeviceGroupFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji grupy urządzeń.

    Grupy są prywatną, plugin-wide konfiguracją (nie per-integracja) — mieszkają
    w tym samym magazynie co instancje integracji, ale są od nich niezależne
    (wizja, sekcja 4.3 i 4.4).
    """

    name: str = Field(description="Wyświetlana nazwa grupy")
    device_ids: list[str] = Field(default_factory=list, description="Lista namespaced ID urządzeń wchodzących w grupę")


class DeviceGroupInstanceConfig(DeviceGroupFileContent):
    """Struktura instancji grupy w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator grupy uzyskany z nazwy pliku")
