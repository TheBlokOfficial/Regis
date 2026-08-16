"""Narzędzia LLM rozszerzenia Home Assistant — `get_state`/`turn_on`/`turn_off`,
adresowane wyłącznie przez `entity_id` (opaque ID, tłumaczony przez Gateway na
wewnętrzny ref zanim wywołanie w ogóle trafi do tego rozszerzenia).
"""

from typing import Any

from server.agent.backend import ToolDefinition, ToolResult
from server.extensions.home_assistant.client import HomeAssistantClient
from server.extensions.home_assistant.models import Device, DeviceGroup
from server.extensions.home_assistant.registry import DeviceRegistry

TOOL_NAMES = ("get_state", "turn_on", "turn_off")

_ENTITY_ID_PARAMETERS = {
    "type": "object",
    "properties": {
        "entity_id": {
            "type": "string",
            "description": "Opaque identyfikator encji (urządzenia lub grupy) z listy dostępnych encji.",
        }
    },
    "required": ["entity_id"],
}


def build_tool_definitions() -> list[ToolDefinition]:
    """Buduje definicje narzędzi rdzenia rozszerzenia dla jednej interakcji agenta."""
    return [
        ToolDefinition(
            name="get_state",
            description="Sprawdź aktualny stan urządzenia lub grupy w Home Assistant po jej entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
        ToolDefinition(
            name="turn_on",
            description="Włącz urządzenie lub wszystkie urządzenia w grupie w Home Assistant po entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
        ToolDefinition(
            name="turn_off",
            description="Wyłącz urządzenie lub wszystkie urządzenia w grupie w Home Assistant po entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
    ]


class HomeAssistantToolExecutor:
    """Wykonuje narzędzia rdzenia na urządzeniu lub grupie znalezionej w rejestrze tej tury."""

    def __init__(self, device_registry: DeviceRegistry, clients: dict[str, HomeAssistantClient]) -> None:
        self._device_registry = device_registry
        self._clients = clients

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        entity_ref = str(arguments.get("entity_id", ""))

        device = self._device_registry.get_device(entity_ref)
        if device is not None:
            if tool_name not in device.capabilities:
                return ToolResult(is_error=True, content=f"Urządzenie '{device.name}' nie obsługuje akcji '{tool_name}'.")
            return await self._invoke_device(device, tool_name)

        group = self._device_registry.get_group(entity_ref)
        if group is not None:
            return await self._invoke_group(group, tool_name)

        return ToolResult(
            is_error=True,
            content=f"Nieznana encja: '{entity_ref}'. Sprawdź aktualną listę dostępnych encji w kontekście.",
        )

    async def _invoke_device(self, device: Device, capability: str) -> ToolResult:
        client = self._clients.get(device.connection_id)
        if client is None:
            return ToolResult(is_error=True, content=f"Połączenie obsługujące urządzenie '{device.name}' jest niedostępne.")
        # device.id nosi przestrzeń nazw połączenia (nadaną przez HomeAssistantExtension) —
        # klient zna wyłącznie swój natywny identyfikator sprzed prefiksu.
        native_id = device.id.split(":", 1)[1] if ":" in device.id else device.id
        return await client.invoke(native_id, capability)

    async def _invoke_group(self, group: DeviceGroup, capability: str) -> ToolResult:
        successes: list[str] = []
        failures: list[str] = []
        for device_id in group.device_ids:
            device = self._device_registry.get_device(device_id)
            if device is None:
                # Nigdy nie ujawniamy surowego, wewnętrznego device_id (namespaced ref
                # połączenia) w treści zwracanej do LLM — nawet ścieżką błędu.
                failures.append("nieznane urządzenie")
                continue
            if capability not in device.capabilities:
                failures.append(f"{device.name} (nie obsługuje akcji)")
                continue
            result = await self._invoke_device(device, capability)
            if result.is_error:
                failures.append(f"{device.name} ({result.content})")
            else:
                successes.append(device.name)

        total = len(group.device_ids)
        summary = f"Grupa '{group.name}': wykonano na {len(successes)}/{total} urządzeniach."
        if failures:
            summary += " Nieudane: " + ", ".join(failures) + "."
        return ToolResult(content=summary, is_error=(not successes and bool(failures)))
