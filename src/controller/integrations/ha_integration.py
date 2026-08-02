"""
Integracja z Home Assistantem w Kontrolerze Regis.

Dziedziczy po BaseIntegration i opakowuje HomeAssistantClient.
"""
import asyncio
from typing import Any
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

    @classmethod
    def from_settings(cls, settings: dict, aliases: dict = None, virtual_groups: dict = None) -> "HomeAssistantIntegration":
        """Tworzy instancję integracji na podstawie ustawień systemowych."""
        default_url = "http://192.168.0.50:8123"
        url = settings.get("ha_url", default_url)
        token = settings.get("ha_token", "TWÓJ_TOKEN_TUTAJ")
        client = HomeAssistantClient(
            url=url,
            token=token,
            aliases=aliases,
            virtual_groups=virtual_groups,
        )
        return cls(client)

    async def check_status(self) -> str:
        """Sprawdza połaczenie z serwerem Home Assistant przez HTTP API."""
        if not self.ha_client:
            return "unknown"
        try:
            await asyncio.to_thread(self.ha_client.check_connection)
            return "online"
        except Exception:
            return "offline"

    # ── Metody integracji ──────────────────────────────────────────────

    @property
    def virtual_groups(self) -> dict:
        return getattr(self.ha_client, "virtual_groups", {}) if self.ha_client else {}

    @property
    def aliases(self) -> dict:
        return getattr(self.ha_client, "aliases", {}) if self.ha_client else {}

    def get_all_states(self) -> dict:
        return self.ha_client.get_all_states() if self.ha_client else {}

    def get_state(self, entity_id: str) -> str:
        return self.ha_client.get_state(entity_id) if self.ha_client else "unavailable"

    def execute_action(self, action: str, entity_id: Any = None, parameters: dict = None) -> bool:
        return self.ha_client.execute_action(action, entity_id, parameters) if self.ha_client else False

    def get_phone_battery(self) -> dict:
        return self.ha_client.get_phone_battery() if self.ha_client else {}

    def _flatten_entities(self, entity_id: str) -> list[str]:
        if self.ha_client and hasattr(self.ha_client, "_flatten_entities"):
            return self.ha_client._flatten_entities(entity_id)
        return [entity_id]

