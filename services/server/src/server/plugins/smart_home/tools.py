"""Narzędzia LLM zaimplementowane raz w pluginie Smart Home, współdzielone przez
wszystkie integracje — `get_state`/`turn_on`/`turn_off`, adresowane wyłącznie
przez `entity_id` (opaque ID, tłumaczony przez Gateway na wewnętrzny ref
zanim wywołanie w ogóle trafi do tego pluginu; wizja, sekcja 4.2).

Żadna z poniższych funkcji nie wie i nie wspomina, która integracja stoi za
danym urządzeniem — cała ta wiedza jest ukryta wewnątrz `DeviceIntegration.invoke()`.
"""

from typing import Any

from server.agent.backend import ToolDefinition, ToolResult
from server.plugins.smart_home.contract import DeviceIntegration
from server.plugins.smart_home.models import Device, DeviceGroup
from server.plugins.smart_home.registry import DeviceRegistry

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
    """Buduje definicje narzędzi rdzenia pluginu dla jednej interakcji agenta."""
    return [
        ToolDefinition(
            name="get_state",
            description="Sprawdź aktualny stan urządzenia lub grupy urządzeń po jej entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
        ToolDefinition(
            name="turn_on",
            description="Włącz urządzenie lub wszystkie urządzenia w grupie po entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
        ToolDefinition(
            name="turn_off",
            description="Wyłącz urządzenie lub wszystkie urządzenia w grupie po entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
    ]


class SmartHomeToolExecutor:
    """Wykonuje narzędzia rdzenia na urządzeniu lub grupie znalezionej w rejestrze tej tury."""

    def __init__(self, device_registry: DeviceRegistry, integrations: dict[str, DeviceIntegration]) -> None:
        self._device_registry = device_registry
        self._integrations = integrations

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
        integration = self._integrations.get(device.integration_id)
        if integration is None:
            return ToolResult(is_error=True, content=f"Integracja obsługująca urządzenie '{device.name}' jest niedostępna.")
        # device.id nosi przestrzeń nazw integracji (nadaną przez SmartHomePlugin) —
        # integracja zna wyłącznie swój natywny identyfikator sprzed prefiksu.
        native_id = device.id.split(":", 1)[1] if ":" in device.id else device.id
        return await integration.invoke(native_id, capability)

    async def _invoke_group(self, group: DeviceGroup, capability: str) -> ToolResult:
        successes: list[str] = []
        failures: list[str] = []
        for device_id in group.device_ids:
            device = self._device_registry.get_device(device_id)
            if device is None:
                failures.append(f"{device_id} (nieznane urządzenie)")
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
