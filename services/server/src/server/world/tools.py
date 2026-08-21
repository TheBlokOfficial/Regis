"""Narzędzia LLM Home Assistant, adresowane wprost przez natywny `entity_id`."""

from typing import Any

from server.agent.llm import ToolDefinition, ToolResult
from server.world.client import HomeAssistantClient
from server.world.models import Device
from server.world.registry import DeviceRegistry

TOOL_NAMES = ("get_state", "turn_on", "turn_off")

_RGB_FEATURES = frozenset({"rgb", "rgbw", "rgbww", "hs", "xy"})

_ENTITY_ID_DESCRIPTION = (
    "entity_id pojedynczego urządzenia lub grupy z listy dostępnych encji, "
    "albo tablica wielu entity_id (urządzeń i/lub grup) do wykonania w jednym wywołaniu."
)

_ENTITY_ID_PARAMETERS = {
    "type": "object",
    "properties": {
        "entity_id": {
            "type": ["string", "array"],
            "items": {"type": "string"},
            "description": _ENTITY_ID_DESCRIPTION,
        }
    },
    "required": ["entity_id"],
}


def build_tool_definitions() -> list[ToolDefinition]:
    """Buduje definicje narzędzi Home Assistant dla jednej interakcji agenta."""
    return [
        ToolDefinition(
            name="get_state",
            description="Sprawdź aktualny stan urządzenia, grupy, albo kilku naraz w Home Assistant po entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
        ToolDefinition(
            name="turn_on",
            description=(
                "Włącz urządzenie, grupę, albo kilka naraz w Home Assistant po entity_id. "
                "Dla świateł można w tym samym wywołaniu opcjonalnie ustawić jasność, kolor/temperaturę "
                "barwową i efekt (te same ustawienia zastosowane do wszystkich podanych encji) — sprawdź "
                "w liście dostępnych encji, które z tych pól dana encja wspiera."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": ["string", "array"],
                        "items": {"type": "string"},
                        "description": _ENTITY_ID_DESCRIPTION,
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
            description="Wyłącz urządzenie, grupę, albo kilka naraz w Home Assistant po entity_id.",
            parameters=_ENTITY_ID_PARAMETERS,
        ),
    ]


class HomeAssistantToolExecutor:
    """Wykonuje narzędzia na jednym urządzeniu, grupie, albo dowolnej tablicy encji naraz
    (urządzenia i grupy mogą się mieszać w tej samej tablicy — grupa rozwija się do swoich
    urządzeń przed wykonaniem)."""

    def __init__(self, device_registry: DeviceRegistry, client: HomeAssistantClient) -> None:
        self._device_registry = device_registry
        self._client = client

    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        raw_ref = arguments.get("entity_id", "")
        entity_refs = raw_ref if isinstance(raw_ref, list) else [raw_ref]
        kwargs = {k: v for k, v in arguments.items() if k != "entity_id"}

        resolved: list[Device] = []
        failures: list[str] = []

        for ref in entity_refs:
            ref = str(ref)
            device = self._device_registry.get_device(ref)
            if device is not None:
                resolved.append(device)
                continue
            group = self._device_registry.get_group(ref)
            if group is not None:
                for device_id in group.device_ids:
                    member = self._device_registry.get_device(device_id)
                    if member is not None:
                        resolved.append(member)
                    else:
                        failures.append(f"nieznane urządzenie w grupie '{group.name}'")
                continue
            failures.append(f"nieznana encja: '{ref}'")

        if not resolved:
            detail = "; ".join(failures) if failures else "brak podanej encji"
            return ToolResult(
                is_error=True,
                content=f"Nie znaleziono żadnej pasującej encji ({detail}). Sprawdź aktualną listę dostępnych encji w kontekście.",
            )

        # Ścieżka pojedynczego urządzenia — bez pośredniej agregacji, zachowuje dzisiejszy,
        # prosty komunikat klienta (np. "Pomyślnie wyłączono urządzenie.").
        if len(resolved) == 1 and not failures:
            device = resolved[0]
            if tool_name not in device.capabilities:
                return ToolResult(is_error=True, content=f"Urządzenie '{device.name}' nie obsługuje akcji '{tool_name}'.")
            if tool_name == "turn_on":
                error = self._validate_turn_on(device, kwargs)
                if error is not None:
                    return error
            return await self._client.invoke(device.id, tool_name, **kwargs)

        # Wiele urządzeń (tablica i/lub rozwinięta grupa) — agregacja częściowego sukcesu.
        successes: list[str] = []
        for device in resolved:
            if tool_name not in device.capabilities:
                failures.append(f"{device.name} (nie obsługuje akcji)")
                continue
            if tool_name == "turn_on":
                error = self._validate_turn_on(device, kwargs)
                if error is not None:
                    failures.append(f"{device.name} ({error.content})")
                    continue
            result = await self._client.invoke(device.id, tool_name, **kwargs)
            if result.is_error:
                failures.append(f"{device.name} ({result.content})")
            else:
                successes.append(device.name)

        total = len(successes) + len(failures)
        summary = f"Wykonano na {len(successes)}/{total} urządzeniach."
        if failures:
            summary += " Nieudane: " + "; ".join(failures) + "."
        return ToolResult(content=summary, is_error=(not successes and bool(failures)))

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
