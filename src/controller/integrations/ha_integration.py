"""
Integracja z Home Assistantem w Kontrolerze Regis.

Dziedziczy po BaseIntegration i opakowuje HomeAssistantClient.
"""
import asyncio
from controller.integrations.base import BaseIntegration
from controller.integrations.ha_client import HomeAssistantClient


class HomeAssistantIntegration(BaseIntegration):
    """Integracja z platformą Home Assistant."""

    def __init__(self, ha_client: HomeAssistantClient):
        super().__init__(
            id="home_assistant",
            name="Home Assistant",
            integration_type="Smart Home",
            detail="Sterowanie urządzeniami & encjami",
        )
        self.ha_client = ha_client

    async def check_status(self) -> str:
        """Sprawdza połaczenie z serwerem Home Assistant przez HTTP API."""
        if not self.ha_client:
            return "unknown"
        try:
            await asyncio.to_thread(self.ha_client.check_connection)
            return "online"
        except Exception:
            return "offline"
