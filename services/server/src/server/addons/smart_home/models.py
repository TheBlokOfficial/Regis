from typing import Any
from pydantic import BaseModel, Field


class IntegrationFileContent(BaseModel):
    """Struktura zawartości pliku JSON instancji integracji (bez duplikacji ID na dysku).

    `type` jest zwykłym stringiem, nie zamkniętym enumem — addon nie zna z góry
    zbioru możliwych integracji, tylko te, które same się w nim zarejestrowały
    (`SmartHomeAddon.register_integration_type`). Nieznany typ jest wykrywany
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
    """Struktura zawartości pliku JSON instancji grupy urządzeń."""

    name: str = Field(description="Wyświetlana nazwa grupy")
    device_ids: list[str] = Field(default_factory=list, description="Lista namespaced ID urządzeń wchodzących w grupę")


class DeviceGroupInstanceConfig(DeviceGroupFileContent):
    """Struktura instancji grupy w pamięci serwera (z identyfikatorem zdekodowanym z nazwy pliku)."""

    id: str = Field(default="", description="Unikalny identyfikator grupy uzyskany z nazwy pliku")
