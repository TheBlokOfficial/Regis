"""
Moduł bazowy dla integracji w Kontrolerze Regis.

Definiuje abstrakcyjną klasę BaseIntegration(ABC), stanowiącą wspólny kontrakt
dla wszystkich integracji zewnętrznych (Home Assistant, MQTT, Zigbee2MQTT itp.).
"""
from abc import ABC, abstractmethod


class BaseIntegration(ABC):
    """Abstrakcyjna klasa bazowa dla integracji zewnętrznych."""

    def __init__(self, id: str, name: str, integration_type: str, detail: str):
        self.id = id
        self.name = name
        self.type = integration_type
        self.detail = detail

    @abstractmethod
    async def check_status(self) -> str:
        """Sprawdza stan połączenia z integracją.

        Musi zwracać jeden ze stanów: 'online', 'offline', 'unknown'.
        """
        pass

    def to_dict(self, status: str) -> dict:
        """Format słownikowy gotowy do przesyłania w REST API (/api/status)."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "detail": self.detail,
            "status": status,
        }
