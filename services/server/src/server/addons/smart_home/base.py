"""Kontrakt Warstwy 2 addonu Smart Home."""

from abc import ABC, abstractmethod
from typing import Any

from server.agent.backend import ToolResult
from server.addons.base import BaseTool
from server.addons.smart_home.devices import Device


class DeviceIntegration(ABC):
    """Abstrakcyjna klasa bazowa dla integracji dostarczającej katalog urządzeń (Warstwa 2).

    Integracja nigdy nie definiuje własnych narzędzi LLM dla standardowych
    akcji — dostarcza wyłącznie katalog `Device` oraz ich egzekucję. Narzędzia
    LLM (`list_devices`/`get_state`/`turn_on`/`turn_off`) implementuje addon
    raz, współdzielone przez wszystkie zarejestrowane integracje (patrz `tools.py`).
    """

    @abstractmethod
    async def list_devices(self) -> list[Device]:
        """Zwraca katalog urządzeń dostarczanych przez tę instancję integracji."""
        pass

    @abstractmethod
    async def invoke(self, device_id: str, capability: str, **kwargs: Any) -> ToolResult:
        """Wykonuje capability na urządzeniu (jedyne miejsce ze znajomością API integracji)."""
        pass

    def get_extra_tools(self) -> list[BaseTool]:
        """Opcjonalne narzędzia integracji, które nie mieszczą się w modelu urządzenie+capability.

        Używać oszczędnie — to jedyne miejsce, gdzie nazwa/opis narzędzia może
        ujawnić konkretną integrację modelowi LLM.
        """
        return []

    async def check_health(self) -> bool:
        """Sprawdza dostępność integracji. Domyślnie zawsze dostępna."""
        return True
