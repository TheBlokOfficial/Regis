"""Narzędzia LLM zaimplementowane raz w addonie Smart Home, współdzielone przez wszystkie integracje.

Żadna z poniższych klas nie wie i nie wspomina, która integracja stoi za danym
urządzeniem — cała ta wiedza jest ukryta wewnątrz `DeviceIntegration.invoke()`.
"""

from typing import Any

from server.agent.backend import ToolDefinition, ToolResult
from server.addons.base import BaseTool
from server.addons.smart_home.base import DeviceIntegration
from server.addons.smart_home.devices import Device, DeviceGroup, DeviceRegistry


def _format_candidates(name: str, candidates: list[Device | DeviceGroup]) -> str:
    names = ", ".join(f"'{c.name}'" for c in candidates)
    return f"Nazwa '{name}' jest niejednoznaczna. Pasujące urządzenia/grupy: {names}. Sprecyzuj nazwę."


class _DeviceLookupMixin:
    """Wspólna logika wyszukiwania urządzenia/grupy i delegacji wywołania do właściwej integracji."""

    def __init__(self, device_registry: DeviceRegistry, integrations: dict[str, DeviceIntegration]) -> None:
        self._device_registry = device_registry
        self._integrations = integrations

    def _resolve(self, name: str) -> Device | DeviceGroup | ToolResult:
        result = self._device_registry.resolve(name)
        if result is None:
            return ToolResult(
                is_error=True,
                content=f"Nie znaleziono urządzenia ani grupy o nazwie '{name}'. Użyj narzędzia list_devices, by zobaczyć dostępne opcje.",
            )
        if isinstance(result, list):
            return ToolResult(is_error=True, content=_format_candidates(name, result))
        return result

    async def _invoke(self, device: Device, capability: str) -> ToolResult:
        integration = self._integrations.get(device.integration_id)
        if integration is None:
            return ToolResult(is_error=True, content=f"Integracja obsługująca urządzenie '{device.name}' jest niedostępna.")
        # device.id nosi przestrzeń nazw integracji (nadaną przez SmartHomeAddon) —
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
            result = await self._invoke(device, capability)
            if result.is_error:
                failures.append(f"{device.name} ({result.content})")
            else:
                successes.append(device.name)

        total = len(group.device_ids)
        summary = f"Grupa '{group.name}': wykonano na {len(successes)}/{total} urządzeniach."
        if failures:
            summary += " Nieudane: " + ", ".join(failures) + "."
        return ToolResult(content=summary, is_error=(not successes and bool(failures)))


class ListDevicesTool(BaseTool):
    """Wylistowanie dostępnych urządzeń i grup, opcjonalnie filtrowanych po obszarze."""

    def __init__(self, device_registry: DeviceRegistry) -> None:
        self._device_registry = device_registry

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="list_devices",
            description="Wylistuj dostępne urządzenia i grupy urządzeń, opcjonalnie filtrując po obszarze.",
            parameters={
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "description": "Nazwa obszaru do filtrowania urządzeń (opcjonalnie).",
                    }
                },
                "required": [],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        area = arguments.get("area")
        devices = self._device_registry.by_area(area)

        lines: list[str] = ["Urządzenia:"]
        if not devices:
            lines.append(f"(brak urządzeń w obszarze '{area}')" if area else "(brak dostępnych urządzeń)")
        for d in devices:
            area_part = f", obszar: {d.area}" if d.area else ""
            actions = ", ".join(sorted(d.capabilities)) or "brak"
            group_names = self._device_registry.group_names_for_device(d.id)
            group_part = f" [grupa: {', '.join(group_names)}]" if group_names else ""
            lines.append(f"- {d.name} (typ: {d.kind}{area_part}, dostępne akcje: {actions}){group_part}")

        if not area:
            groups = self._device_registry.all_groups()
            lines.append("")
            lines.append("Grupy:")
            if not groups:
                lines.append("(brak zdefiniowanych grup)")
            for g in groups:
                member_names = [
                    dev.name for dev_id in g.device_ids if (dev := self._device_registry.get_device(dev_id)) is not None
                ]
                lines.append(f"- {g.name} (obejmuje: {', '.join(member_names) or 'brak'})")

        return ToolResult(content="\n".join(lines))


class GetStateTool(_DeviceLookupMixin, BaseTool):
    """Odczyt aktualnego stanu urządzenia lub grupy po przyjaznej nazwie."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="get_state",
            description="Sprawdź aktualny stan urządzenia lub grupy urządzeń po nazwie.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Przyjazna nazwa urządzenia lub grupy."}},
                "required": ["name"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        resolved = self._resolve(name)
        if isinstance(resolved, ToolResult):
            return resolved
        if isinstance(resolved, DeviceGroup):
            return await self._invoke_group(resolved, "get_state")
        if "get_state" not in resolved.capabilities:
            return ToolResult(is_error=True, content=f"Urządzenie '{resolved.name}' nie obsługuje odczytu stanu.")
        return await self._invoke(resolved, "get_state")


class TurnOnTool(_DeviceLookupMixin, BaseTool):
    """Włączenie urządzenia lub całej grupy po przyjaznej nazwie."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="turn_on",
            description="Włącz urządzenie lub wszystkie urządzenia w grupie po nazwie.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Przyjazna nazwa urządzenia lub grupy."}},
                "required": ["name"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        resolved = self._resolve(name)
        if isinstance(resolved, ToolResult):
            return resolved
        if isinstance(resolved, DeviceGroup):
            return await self._invoke_group(resolved, "turn_on")
        if "turn_on" not in resolved.capabilities:
            return ToolResult(is_error=True, content=f"Urządzenie '{resolved.name}' nie obsługuje włączania.")
        return await self._invoke(resolved, "turn_on")


class TurnOffTool(_DeviceLookupMixin, BaseTool):
    """Wyłączenie urządzenia lub całej grupy po przyjaznej nazwie."""

    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="turn_off",
            description="Wyłącz urządzenie lub wszystkie urządzenia w grupie po nazwie.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Przyjazna nazwa urządzenia lub grupy."}},
                "required": ["name"],
            },
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name = str(arguments.get("name", ""))
        resolved = self._resolve(name)
        if isinstance(resolved, ToolResult):
            return resolved
        if isinstance(resolved, DeviceGroup):
            return await self._invoke_group(resolved, "turn_off")
        if "turn_off" not in resolved.capabilities:
            return ToolResult(is_error=True, content=f"Urządzenie '{resolved.name}' nie obsługuje wyłączania.")
        return await self._invoke(resolved, "turn_off")


def build_core_tools(device_registry: DeviceRegistry, integrations: dict[str, DeviceIntegration]) -> list[BaseTool]:
    """Buduje instancje wszystkich narzędzi rdzenia addonu dla jednej interakcji agenta."""
    return [
        ListDevicesTool(device_registry),
        GetStateTool(device_registry, integrations),
        TurnOnTool(device_registry, integrations),
        TurnOffTool(device_registry, integrations),
    ]
