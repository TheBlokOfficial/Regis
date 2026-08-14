"""Kontrakt Warstwy 2 (integracja) pluginu Smart Home — prywatna sprawa pluginu.

Nigdy widoczny dla Gateway ani agenta — to plugin orkiestruje integracje
implementujące ten kontrakt (wizja, sekcja 2, "Integracja").
"""

from abc import ABC, abstractmethod
from typing import Any

from server.agent.backend import ToolResult
from server.plugins.smart_home.models import Device


class DeviceIntegration(ABC):
    """Abstrakcyjna klasa bazowa dla integracji dostarczającej katalog urządzeń.

    Integracja nigdy nie definiuje własnych narzędzi LLM — dostarcza
    wyłącznie katalog `Device` oraz ich egzekucję. Narzędzia LLM
    (`get_state`/`turn_on`/`turn_off`) implementuje plugin raz, współdzielone
    przez wszystkie zarejestrowane integracje (patrz `tools.py`).
    """

    @abstractmethod
    async def list_devices(self) -> list[Device]:
        """Zwraca katalog urządzeń dostarczanych przez tę instancję integracji."""
        pass

    @abstractmethod
    async def invoke(self, device_id: str, capability: str, **kwargs: Any) -> ToolResult:
        """Wykonuje capability na urządzeniu (jedyne miejsce ze znajomością API integracji)."""
        pass

    async def check_health(self) -> bool:
        """Sprawdza dostępność integracji. Domyślnie zawsze dostępna."""
        return True
