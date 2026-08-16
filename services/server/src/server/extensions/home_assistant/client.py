"""Klient REST API Home Assistant.

Cała wiedza o formacie danych Home Assistant (entity_id, domain.service,
atrybuty encji) jest zamknięta w tej klasie — narzędzia LLM rozszerzenia
(`tools.py`) operują wyłącznie na generycznym modelu `Device`+capability.
"""

from typing import Any

import httpx
from shared import get_logger

from server.agent.backend import ToolResult
from server.extensions.home_assistant.models import Device

logger = get_logger("regis.extensions.home_assistant")

# Domeny encji HA obsługujące włączanie/wyłączanie — wszystkie pozostałe domeny
# udostępniają wyłącznie odczyt stanu ('get_state').
_TOGGLEABLE_DOMAINS = {"light", "switch", "fan", "input_boolean"}


def _capabilities_for_domain(domain: str) -> set[str]:
    if domain in _TOGGLEABLE_DOMAINS:
        return {"turn_on", "turn_off", "get_state"}
    return {"get_state"}


def _format_state_text(entity_id: str, domain: str, state: str, attributes: dict[str, Any]) -> str:
    """Formatuje surowy stan encji HA na czytelny tekst — jedyne miejsce, gdzie interpretujemy atrybuty HA."""
    friendly = attributes.get("friendly_name", entity_id)

    if domain == "sensor":
        unit = attributes.get("unit_of_measurement", "")
        return f"{friendly}: {state}{f' {unit}' if unit else ''}"

    if domain == "climate":
        parts = [f"tryb: {state}"]
        current = attributes.get("current_temperature")
        target = attributes.get("temperature")
        if current is not None:
            parts.append(f"aktualna temperatura: {current}°C")
        if target is not None:
            parts.append(f"temperatura docelowa: {target}°C")
        return f"{friendly}: " + ", ".join(parts)

    if domain in _TOGGLEABLE_DOMAINS:
        status = {"on": "włączone", "off": "wyłączone"}.get(state, state)
        return f"{friendly}: {status}"

    return f"{friendly}: {state}"


class HomeAssistantClient:
    """Komunikuje się z REST API jednego połączenia Home Assistant."""

    def __init__(self, base_url: str, access_token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def list_devices(self) -> list[Device]:
        url = f"{self.base_url}/api/states"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url, headers=self._headers())
                response.raise_for_status()
                entities = response.json()
        except Exception as e:
            logger.error(f"Nie udało się pobrać listy encji z Home Assistant [{self.base_url}]: {e}")
            return []

        devices: list[Device] = []
        for entity in entities:
            entity_id = entity.get("entity_id", "")
            if "." not in entity_id:
                continue
            domain = entity_id.split(".", 1)[0]
            attributes = entity.get("attributes", {})
            devices.append(
                Device(
                    id=entity_id,
                    connection_id="",  # uzupełniane przez HomeAssistantExtension po zwrocie
                    name=attributes.get("friendly_name", entity_id),
                    kind=domain,
                    capabilities=_capabilities_for_domain(domain),
                    area=attributes.get("area_id"),
                )
            )
        return devices

    async def invoke(self, device_id: str, capability: str, **kwargs: Any) -> ToolResult:
        entity_id = device_id
        domain = entity_id.split(".", 1)[0] if "." in entity_id else ""

        if capability == "get_state":
            url = f"{self.base_url}/api/states/{entity_id}"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(url, headers=self._headers())
                    response.raise_for_status()
                    data = response.json()
            except Exception as e:
                logger.error(f"Błąd odczytu stanu encji '{entity_id}' z Home Assistant: {e}")
                return ToolResult(is_error=True, content=f"Nie udało się odczytać stanu urządzenia: {e}")
            text = _format_state_text(entity_id, domain, data.get("state", "unknown"), data.get("attributes", {}))
            return ToolResult(content=text)

        if capability in ("turn_on", "turn_off"):
            url = f"{self.base_url}/api/services/{domain}/{capability}"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(url, headers=self._headers(), json={"entity_id": entity_id})
                    response.raise_for_status()
            except Exception as e:
                logger.error(f"Błąd wywołania usługi '{capability}' na encji '{entity_id}' w Home Assistant: {e}")
                return ToolResult(is_error=True, content=f"Nie udało się wykonać akcji: {e}")
            action_text = "włączono" if capability == "turn_on" else "wyłączono"
            return ToolResult(content=f"Pomyślnie {action_text} urządzenie.")

        return ToolResult(is_error=True, content=f"Nieobsługiwana akcja: '{capability}'.")

    async def check_health(self) -> bool:
        url = f"{self.base_url}/api/"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=self._headers())
                return response.status_code == 200
        except Exception:
            return False
