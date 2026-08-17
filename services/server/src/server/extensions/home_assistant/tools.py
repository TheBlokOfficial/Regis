"""Narzędzia LLM rozszerzenia Home Assistant, adresowane wyłącznie przez
`entity_id` (opaque ID, tłumaczony przez Gateway na wewnętrzny ref zanim
wywołanie w ogóle trafi do tego rozszerzenia).
"""

from typing import Any

from server.agent.backend import ToolDefinition, ToolResult
from server.extensions.home_assistant.client import HomeAssistantClient
from server.extensions.home_assistant.models import Device, DeviceGroup
from server.extensions.home_assistant.registry import DeviceRegistry

TOOL_NAMES = ("get_state", "turn_on", "turn_off")

_RGB_FEATURES = frozenset({"rgb", "rgbw", "rgbww", "hs", "xy"})

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
            description=(
                "Włącz urządzenie lub wszystkie urządzenia w grupie w Home Assistant po entity_id. "
                "Dla świateł można w tym samym wywołaniu opcjonalnie ustawić jasność, kolor/temperaturę "
                "barwową i efekt — sprawdź w liście dostępnych encji, które z tych pól dana encja wspiera."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "string",
                        "description": "Opaque identyfikator encji (urządzenia lub grupy) z listy dostępnych encji.",
                    },
                    "brightness_pct": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Tylko światła wspierające jasność (cecha 'brightness'): jasność w procentach (0-100).",
                    },
                    "color_temp_kelvin": {
                        "type": "integer",
                        "description": (
                            "Tylko światła wspierające 'color_temp': temperatura barwowa w Kelvinach "
                            "(biel ciepła/zimna). Wyklucza się z rgb_color."
                        ),
                    },
                    "rgb_color": {
                        "type": "array",
                        "items": {"type": "integer", "minimum": 0, "maximum": 255},
                        "minItems": 3,
                        "maxItems": 3,
                        "description": (
                            "Tylko światła wspierające kolor RGB ('rgb'/'rgbw'/'rgbww'/'hs'/'xy'): [R, G, B], "
                            "0-255 każdy. Wyklucza się z color_temp_kelvin."
                        ),
                    },
                    "effect": {
                        "type": "string",
                        "description": "Tylko światła wspierające 'effect': nazwa efektu z listy dostępnych dla tej encji.",
                    },
                },
                "required": ["entity_id"],
            },
        ),
        ToolDefinition(
            name="turn_off",
            description="Wyłącz urządzenie lub wszystkie urządzenia w grupie w Home Assistant po entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
    ]


class HomeAssistantToolExecutor:
    """Wykonuje narzędzia rdzenia na urządzeniu lub grupie znalezionej w rejestrze tej tury."""

    def __init__(self, device_registry: DeviceRegistry, client: HomeAssistantClient) -> None:
        self._device_registry = device_registry
        self._client = client

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        entity_ref = str(arguments.get("entity_id", ""))
        kwargs = {k: v for k, v in arguments.items() if k != "entity_id"}

        device = self._device_registry.get_device(entity_ref)
        if device is not None:
            if tool_name not in device.capabilities:
                return ToolResult(is_error=True, content=f"Urządzenie '{device.name}' nie obsługuje akcji '{tool_name}'.")
            if tool_name == "turn_on":
                error = self._validate_turn_on(device, kwargs)
                if error is not None:
                    return error
            return await self._invoke_device(device, tool_name, **kwargs)

        group = self._device_registry.get_group(entity_ref)
        if group is not None:
            return await self._invoke_group(group, tool_name, **kwargs)

        return ToolResult(
            is_error=True,
            content=f"Nieznana encja: '{entity_ref}'. Sprawdź aktualną listę dostępnych encji w kontekście.",
        )

    @staticmethod
    def _validate_turn_on(device: Device, kwargs: dict[str, Any]) -> ToolResult | None:
        """Sprawdza opcjonalne pola światła w `turn_on` względem cech zapisanych pod `device.capabilities["turn_on"]`."""
        brightness = kwargs.get("brightness_pct")
        color_temp = kwargs.get("color_temp_kelvin")
        rgb = kwargs.get("rgb_color")
        effect = kwargs.get("effect")
        if color_temp is not None and rgb is not None:
            return ToolResult(
                is_error=True,
                content="Podaj co najwyżej jedno z: color_temp_kelvin, rgb_color.",
            )
        features = device.capabilities.get("turn_on", frozenset())
        if brightness is not None and "brightness" not in features:
            return ToolResult(is_error=True, content=f"Urządzenie '{device.name}' nie obsługuje regulacji jasności.")
        if color_temp is not None and "color_temp" not in features:
            return ToolResult(is_error=True, content=f"Urządzenie '{device.name}' nie obsługuje temperatury barwowej.")
        if rgb is not None and not (features & _RGB_FEATURES):
            return ToolResult(is_error=True, content=f"Urządzenie '{device.name}' nie obsługuje koloru RGB.")
        if effect is not None and "effect" not in features:
            return ToolResult(is_error=True, content=f"Urządzenie '{device.name}' nie obsługuje efektów świetlnych.")
        return None

    async def _invoke_device(self, device: Device, capability: str, **kwargs: Any) -> ToolResult:
        return await self._client.invoke(device.id, capability, **kwargs)

    async def _invoke_group(self, group: DeviceGroup, capability: str, **kwargs: Any) -> ToolResult:
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
            if capability == "turn_on":
                error = self._validate_turn_on(device, kwargs)
                if error is not None:
                    failures.append(f"{device.name} ({error.content})")
                    continue
            result = await self._invoke_device(device, capability, **kwargs)
            if result.is_error:
                failures.append(f"{device.name} ({result.content})")
            else:
                successes.append(device.name)

        total = len(group.device_ids)
        summary = f"Grupa '{group.name}': wykonano na {len(successes)}/{total} urządzeniach."
        if failures:
            summary += " Nieudane: " + ", ".join(failures) + "."
        return ToolResult(content=summary, is_error=(not successes and bool(failures)))
