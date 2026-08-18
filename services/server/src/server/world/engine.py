"""WorldEngine — jedyne ramię agenta dotykające świata zewnętrznego.

Implementuje `server.agent.context_provider.WorldInterface` strukturalnie
(bez importu — kernel nigdy nie importuje `server.world`, tylko odwrotnie).
Wewnątrz woła wprost swoje własne backendy (klient Home Assistant, rejestr
satelit) — zero protokołu między nimi, bo to jeden, konkretny silnik, nie
generyczna kolekcja wymiennych rozszerzeń.

Kolejność w `build()` jest świadoma: rejestracja satelity (kanał, lokalizacja)
liczona jest niezależnie od dostępności Home Assistant — brak/nieosiągalność
configu ucina wyłącznie encje/narzędzia HA, nigdy framing kanału komunikacji.
"""

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from shared import ConfigStore, get_logger, get_service_root, sanitize_identifier

from server.agent.backend import ToolDefinition, ToolResult
from server.agent.context_provider import ContextBuild
from server.world.client import HomeAssistantClient
from server.world.models import (
    DeclaredDeviceEntry,
    DeclaredDevicesFileContent,
    Device,
    DeviceGroup,
    DeviceGroupFileContent,
    DeviceGroupInstanceConfig,
    HomeAssistantConfig,
    SatelliteRegistration,
    SatelliteRegistrationsFileContent,
)
from server.world.registry import DeviceRegistry
from server.world.tools import HomeAssistantToolExecutor, TOOL_NAMES, build_tool_definitions

logger = get_logger("regis.world")

ClientFactoryFn = Callable[[HomeAssistantConfig], HomeAssistantClient]

_GET_TIME_TOOL = "get_time"


class WorldEngine:
    """Jedyny silnik świata — konfiguracja Home Assistant (singleton), zadeklarowane
    urządzenia, grupy i rejestr satelit. Implementuje `WorldInterface`."""

    def __init__(self, data_dir: Optional[Path] = None, client_factory: Optional[ClientFactoryFn] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data" / "world")).resolve()
        self.groups_dir = self.base_data_dir / "groups"
        self.config_path = self.base_data_dir / "config.json"
        self.declared_devices_path = self.base_data_dir / "declared_devices.json"
        self.satellites_path = self.base_data_dir / "satellites.json"
        self._lock = asyncio.Lock()
        self._defaults_ensured = False
        self._client_factory = client_factory

    async def _ensure_defaults(self) -> None:
        """Tworzy katalog grup jeśli nie istnieje. Silnik startuje bez konfiguracji i grup."""
        if self._defaults_ensured:
            return
        async with self._lock:
            if self._defaults_ensured:
                return
            self.groups_dir.mkdir(parents=True, exist_ok=True)
            self._defaults_ensured = True

    def _build_client(self, config: HomeAssistantConfig) -> HomeAssistantClient:
        if self._client_factory is not None:
            return self._client_factory(config)
        return HomeAssistantClient(base_url=config.base_url, access_token=config.access_token)

    # --------------------------------------------------------------------------
    # Konfiguracja singletona Home Assistant
    # --------------------------------------------------------------------------

    async def get_config(self) -> HomeAssistantConfig:
        """Wczytuje konfigurację. Puste pola oznaczają brak konfiguracji."""
        await self._ensure_defaults()
        return await asyncio.to_thread(ConfigStore(HomeAssistantConfig, self.config_path).load)

    async def save_config(self, base_url: str, access_token: str) -> HomeAssistantConfig:
        """Zapisuje adres serwera i token dostępu."""
        await self._ensure_defaults()
        content = HomeAssistantConfig(base_url=base_url, access_token=access_token)
        async with self._lock:
            await asyncio.to_thread(ConfigStore(HomeAssistantConfig, self.config_path).save, content)
        logger.info("Zaktualizowano konfigurację Home Assistant.")
        return content

    # --------------------------------------------------------------------------
    # CRUD grup urządzeń
    # --------------------------------------------------------------------------

    async def create_group(
        self,
        name: str,
        device_ids: list[str],
        custom_id: Optional[str] = None,
    ) -> DeviceGroupInstanceConfig:
        """Tworzy nową grupę urządzeń i zapisuje ją w pliku JSON."""
        await self._ensure_defaults()
        group_id = custom_id or f"grp_{uuid.uuid4().hex[:8]}"
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        content = DeviceGroupFileContent(name=name, device_ids=device_ids)
        file_path = self.groups_dir / f"{group_id}.json"

        async with self._lock:
            await asyncio.to_thread(ConfigStore(DeviceGroupFileContent, file_path).save, content)

        logger.info(f"Utworzono nową grupę [{name}] z ID: {group_id}")
        return DeviceGroupInstanceConfig(id=group_id, **content.model_dump())

    async def list_groups(self) -> dict[str, DeviceGroupInstanceConfig]:
        """Wczytuje i zwraca słownik wszystkich zadeklarowanych grup {id: config}."""
        await self._ensure_defaults()
        instances: dict[str, DeviceGroupInstanceConfig] = {}

        async with self._lock:
            for file_path in sorted(self.groups_dir.glob("*.json")):
                try:
                    group_id = file_path.stem
                    content = await asyncio.to_thread(ConfigStore(DeviceGroupFileContent, file_path).load)
                    instances[group_id] = DeviceGroupInstanceConfig(id=group_id, **content.model_dump())
                except Exception as e:
                    logger.error(f"Błąd podczas wczytywania pliku grupy [{file_path}]: {e}")

        return instances

    async def update_group(
        self,
        group_id: str,
        name: str | None = None,
        device_ids: list[str] | None = None,
    ) -> DeviceGroupInstanceConfig:
        """Aktualizuje wybrane pola istniejącej grupy. Rzuca ValueError jeśli nie istnieje."""
        sanitize_identifier(group_id, field_name="group_id")
        await self._ensure_defaults()
        file_path = self.groups_dir / f"{group_id}.json"
        if not file_path.exists():
            raise ValueError(f"Grupa o ID '{group_id}' nie istnieje.")

        async with self._lock:
            existing = await asyncio.to_thread(ConfigStore(DeviceGroupFileContent, file_path).load)
            updated = DeviceGroupFileContent(
                name=name if name is not None else existing.name,
                device_ids=device_ids if device_ids is not None else existing.device_ids,
            )
            await asyncio.to_thread(ConfigStore(DeviceGroupFileContent, file_path).save, updated)

        logger.info(f"Zaktualizowano grupę [{group_id}].")
        return DeviceGroupInstanceConfig(id=group_id, **updated.model_dump())

    async def delete_group(self, group_id: str) -> bool:
        """Usuwa plik grupy z dysku."""
        sanitize_identifier(group_id, field_name="group_id")
        await self._ensure_defaults()
        async with self._lock:
            file_path = self.groups_dir / f"{group_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Usunięto grupę [{group_id}] z dysku.")
                return True
            return False

    # --------------------------------------------------------------------------
    # Zadeklarowane urządzenia — jedyne źródło prawdy o tym, co widzi agent
    # --------------------------------------------------------------------------

    async def get_declared_devices(self) -> DeclaredDevicesFileContent:
        """Wczytuje zadeklarowaną listę urządzeń. Brak pliku = pusta lista."""
        await self._ensure_defaults()
        return await asyncio.to_thread(ConfigStore(DeclaredDevicesFileContent, self.declared_devices_path).load)

    async def _save_declared_devices(self, content: DeclaredDevicesFileContent) -> None:
        await self._ensure_defaults()
        async with self._lock:
            await asyncio.to_thread(ConfigStore(DeclaredDevicesFileContent, self.declared_devices_path).save, content)

    async def add_declared_device(self, entity_id: str, display_name: str | None = None) -> None:
        """Dodaje encję do zadeklarowanej listy (widoczna dla agenta od tej pory)."""
        current = await self.get_declared_devices()
        current.entries[entity_id] = DeclaredDeviceEntry(display_name=display_name)
        await self._save_declared_devices(current)
        logger.info(f"Zadeklarowano urządzenie [{entity_id}].")

    async def update_declared_device(self, entity_id: str, display_name: str | None) -> DeclaredDeviceEntry:
        """Zmienia `display_name` istniejącego wpisu. Rzuca ValueError jeśli nie istnieje."""
        current = await self.get_declared_devices()
        if entity_id not in current.entries:
            raise ValueError(f"Urządzenie '{entity_id}' nie jest zadeklarowane.")
        current.entries[entity_id] = DeclaredDeviceEntry(display_name=display_name)
        await self._save_declared_devices(current)
        return current.entries[entity_id]

    async def remove_declared_device(self, entity_id: str) -> bool:
        """Usuwa encję z zadeklarowanej listy (przestaje być widoczna dla agenta)."""
        current = await self.get_declared_devices()
        if entity_id not in current.entries:
            return False
        del current.entries[entity_id]
        await self._save_declared_devices(current)
        logger.info(f"Usunięto deklarację urządzenia [{entity_id}].")
        return True

    # --------------------------------------------------------------------------
    # Katalog surowy i zadeklarowane urządzenia po zjoinowaniu ze stanem HA
    # --------------------------------------------------------------------------

    async def get_catalog(self, client: HomeAssistantClient | None = None) -> list[Device]:
        """Zwraca surowy katalog wszystkich encji HA (bez filtra deklaracji) — do wyszukiwarki w UI."""
        if client is None:
            config = await self.get_config()
            if not config.base_url or not config.access_token:
                return []
            client = self._build_client(config)
        return await client.list_devices()

    async def resolve_devices(self, client: HomeAssistantClient | None = None) -> list[Device]:
        """Zwraca zadeklarowane urządzenia zjoinowane z aktualnym stanem HA (join po `entity_id`).

        Encja zadeklarowana, która zniknęła po stronie HA, jest po cichu
        pomijana — nie ma tam czego zjoinować.
        """
        declared = await self.get_declared_devices()
        if not declared.entries:
            return []

        raw_devices = await self.get_catalog(client=client)
        raw_by_id = {d.id: d for d in raw_devices}

        result: list[Device] = []
        for entity_id, entry in declared.entries.items():
            raw = raw_by_id.get(entity_id)
            if raw is None:
                continue
            name = entry.display_name if entry.display_name else raw.name
            result.append(Device(id=entity_id, name=name, kind=raw.kind, capabilities=raw.capabilities, area=raw.area))
        return result

    async def list_areas(self) -> list[str]:
        """Unikalne, niepuste `area_id` wśród zadeklarowanych urządzeń — wygoda formularza rejestracji satelity."""
        devices = await self.resolve_devices()
        return sorted({d.area for d in devices if d.area})

    # --------------------------------------------------------------------------
    # Rejestr satelit — sender_id -> pokój + kanał komunikacji
    # --------------------------------------------------------------------------

    async def get_satellites(self) -> SatelliteRegistrationsFileContent:
        """Wczytuje rejestr satelit. Brak pliku = pusty rejestr."""
        await self._ensure_defaults()
        return await asyncio.to_thread(ConfigStore(SatelliteRegistrationsFileContent, self.satellites_path).load)

    async def _save_satellites(self, content: SatelliteRegistrationsFileContent) -> None:
        await self._ensure_defaults()
        async with self._lock:
            await asyncio.to_thread(ConfigStore(SatelliteRegistrationsFileContent, self.satellites_path).save, content)

    async def register_satellite(self, sender_id: str, registration: SatelliteRegistration) -> SatelliteRegistration:
        """Rejestruje lub nadpisuje rejestrację satelity dla danego `sender_id`."""
        current = await self.get_satellites()
        current.entries[sender_id] = registration
        await self._save_satellites(current)
        logger.info(f"Zarejestrowano satelitę [{sender_id}].")
        return registration

    async def remove_satellite(self, sender_id: str) -> bool:
        """Usuwa rejestrację satelity."""
        current = await self.get_satellites()
        if sender_id not in current.entries:
            return False
        del current.entries[sender_id]
        await self._save_satellites(current)
        logger.info(f"Usunięto rejestrację satelity [{sender_id}].")
        return True

    # --------------------------------------------------------------------------
    # WorldInterface — budowanie wkładu na czas jednej interakcji agenta
    # --------------------------------------------------------------------------

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        context_parts: list[str] = []
        now_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        context_parts.append(f"Aktualna data i godzina: {now_value}.")

        # 1. Rejestracja satelity — niezależnie od dostępności Home Assistant.
        registration: SatelliteRegistration | None = None
        if sender_id is not None:
            satellites = await self.get_satellites()
            registration = satellites.entries.get(sender_id)
        if registration is not None:
            if registration.channel == "voice":
                context_parts.append(
                    "Nadawca komunikuje się głosem — odpowiadaj krótkimi zdaniami, "
                    "unikaj Markdown i list, dobierz treść pod syntezę mowy."
                )
            else:
                context_parts.append("Nadawca komunikuje się tekstowo.")
            if registration.room_label:
                context_parts.append(f"Nadawca znajduje się w lokalizacji: {registration.room_label}.")

        # 2. Home Assistant — łagodna degradacja, nie wpływa na framing z kroku 1.
        config = await self.get_config()
        devices: list[Device] = []
        groups: list[DeviceGroup] = []
        client: HomeAssistantClient | None = None
        if config.base_url and config.access_token:
            client = self._build_client(config)
            devices = await self.resolve_devices(client=client)
            group_instances = await self.list_groups()
            groups = [DeviceGroup(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids) for cfg in group_instances.values()]

        if devices or groups:
            context_parts.append(
                self._render_devices_section(
                    devices,
                    groups,
                    current_room_key=registration.room_key if registration else None,
                    current_room_label=registration.room_label if registration else None,
                )
            )

        # 3. Narzędzia + dispatch
        tool_definitions: list[ToolDefinition] = [
            ToolDefinition(
                name=_GET_TIME_TOOL,
                description="Zwraca aktualną datę i godzinę.",
                parameters={"type": "object", "properties": {}},
            )
        ]
        executor: HomeAssistantToolExecutor | None = None
        if devices or groups:
            tool_definitions.extend(build_tool_definitions())
            device_registry = DeviceRegistry(devices, groups)
            executor = HomeAssistantToolExecutor(device_registry, client) if client is not None else None

        async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            if name == _GET_TIME_TOOL:
                return ToolResult(content=now_value)
            if executor is not None:
                try:
                    return await executor.execute(name, arguments)
                except Exception as e:
                    logger.error(f"Błąd podczas wykonania narzędzia [{name}]: {e}")
                    return ToolResult(is_error=True, content=f"Błąd wykonania narzędzia '{name}': {e}")
            return ToolResult(is_error=True, content=f"Nieznane narzędzie: '{name}'.")

        return ContextBuild(
            tool_definitions=tool_definitions,
            dynamic_context="\n\n".join(context_parts),
            dispatch=dispatch,
        )

    @staticmethod
    def _render_devices_section(
        devices: list[Device],
        groups: list[DeviceGroup],
        current_room_key: str | None,
        current_room_label: str | None = None,
    ) -> str:
        """Renderuje listę urządzeń posegregowaną wg pokoju (`Device.area`) — pełna
        adresowalność zawsze zachowana, segregacja to wyłącznie prezentacja."""
        by_room: dict[str, list[Device]] = {}
        unassigned: list[Device] = []
        for device in devices:
            if device.area:
                by_room.setdefault(device.area, []).append(device)
            else:
                unassigned.append(device)

        lines = ["Dostępne urządzenia (adresuj je po podanym entity_id):"]
        for room, room_devices in sorted(by_room.items(), key=lambda item: item[0] != current_room_key):
            is_current = room == current_room_key
            label = current_room_label if (is_current and current_room_label) else room
            header = f"### {label}" + (" (Twoja lokalizacja)" if is_current else "")
            lines.append(header)
            for device in room_devices:
                lines.append(f"- [{device.id}] {device.name} (możliwości: {_format_capabilities(device)})")
        if unassigned:
            lines.append("### (bez przypisanego pokoju)")
            for device in unassigned:
                lines.append(f"- [{device.id}] {device.name} (możliwości: {_format_capabilities(device)})")
        if groups:
            lines.append("### Grupy")
            group_capabilities = ", ".join(TOOL_NAMES)
            for group in groups:
                lines.append(f"- [{group.id}] {group.name} (możliwości: {group_capabilities})")
        return "\n".join(lines)


def _format_capabilities(device: Device) -> str:
    labels = []
    for tool_name, features in sorted(device.capabilities.items()):
        labels.append(f"{tool_name}[{', '.join(sorted(features))}]" if features else tool_name)
    return ", ".join(labels) if labels else "brak"
