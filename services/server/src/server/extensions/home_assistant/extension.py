"""HomeAssistantExtension — jedyny byt widoczny dla Gateway w tej domenie.

Spełnia strukturalnie `PluginProvider` (`agent/plugin_contract.py`) i
`NetworkExtension` (`network/extension_contract.py`) — jeden identyfikator
(`plugin_id == extension_id == "home_assistant"`) na obu granicach, plus
opcjonalnie na trzeciej: kluczu rejestru widoków frontendu.

Home Assistant jest traktowany jako jeden, globalny zasób (singleton) — nie
kolekcja nazwanych połączeń. Katalog urządzeń widocznych dla agenta jest
opt-in: nic nie jest widoczne, dopóki nie zostanie świadomie dodane do
zadeklarowanej listy.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from shared import ConfigStore, get_logger, get_service_root, sanitize_identifier

from server.agent.backend import ToolResult
from server.agent.plugin_contract import EntityCapability, EntitySpec, Fact, PluginContribution
from server.extensions._shared.state import ExtensionStateFileContent
from server.extensions.home_assistant.client import HomeAssistantClient
from server.extensions.home_assistant.models import (
    DeclaredDeviceEntry,
    DeclaredDevicesFileContent,
    Device,
    DeviceGroup,
    DeviceGroupFileContent,
    DeviceGroupInstanceConfig,
    HomeAssistantConfig,
)
from server.extensions.home_assistant.registry import DeviceRegistry
from server.extensions.home_assistant.routes import create_home_assistant_router
from server.extensions.home_assistant.tools import HomeAssistantToolExecutor, build_tool_definitions, TOOL_NAMES

logger = get_logger("regis.extensions.home_assistant")

ClientFactoryFn = Callable[[HomeAssistantConfig], HomeAssistantClient]

# Grupa jest z zewnątrz nieodróżnialna od pojedynczego urządzenia — deklaruje
# więc zawsze wszystkie narzędzia rdzenia; gating per-członek następuje
# dopiero przy wykonaniu (patrz `tools.py`).
_GROUP_CAPABILITIES = frozenset(EntityCapability(tool_name=name) for name in TOOL_NAMES)


class HomeAssistantExtension:
    """Rozszerzenie Home Assistant — spełnia `PluginProvider` i `NetworkExtension`.

    Nie dziedziczy jawnie po żadnym z tych protokołów (strukturalne typowanie)
    — pasuje kształtem dzięki `plugin_id`/`extension_id`/`label` i metodom.
    """

    plugin_id = "home_assistant"
    extension_id = "home_assistant"
    label = "Home Assistant"

    def __init__(self, data_dir: Optional[Path] = None, client_factory: Optional[ClientFactoryFn] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data" / "extensions" / "home_assistant")).resolve()
        self.groups_dir = self.base_data_dir / "groups"
        self.config_path = self.base_data_dir / "config.json"
        self.declared_devices_path = self.base_data_dir / "declared_devices.json"
        self.state_path = self.base_data_dir / "state.json"
        self._lock = asyncio.Lock()
        self._defaults_ensured = False
        self._client_factory = client_factory

    async def _ensure_defaults(self) -> None:
        """Tworzy katalog grup jeśli nie istnieje. Rozszerzenie startuje bez konfiguracji i grup."""
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
    # NetworkExtension — przełącznik enabled całego rozszerzenia
    # --------------------------------------------------------------------------

    async def is_enabled(self) -> bool:
        state = await asyncio.to_thread(ConfigStore(ExtensionStateFileContent, self.state_path).load)
        return state.enabled

    async def set_enabled(self, value: bool) -> None:
        await asyncio.to_thread(ConfigStore(ExtensionStateFileContent, self.state_path).save, ExtensionStateFileContent(enabled=value))

    def build_router(self):
        return create_home_assistant_router(self)

    # --------------------------------------------------------------------------
    # Konfiguracja singletona Home Assistant
    # --------------------------------------------------------------------------

    async def get_config(self) -> HomeAssistantConfig:
        """Wczytuje konfigurację. Puste pola oznaczają rozszerzenie nieskonfigurowane."""
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
    # CRUD grup urządzeń — prywatna, rozszerzenie-wide konfiguracja
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

    # --------------------------------------------------------------------------
    # PluginProvider — budowanie wkładu na czas jednej interakcji agenta
    # --------------------------------------------------------------------------

    async def build(self, facts: list[Fact]) -> PluginContribution:
        """Buduje pełny, spłaszczony wkład rozszerzenia na czas jednej interakcji agenta.

        :param facts: Fakty zebrane w tej turze przez Gateway — nieużywane
            przez to rozszerzenie.
        """
        del facts

        async def _empty_dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            return ToolResult(is_error=True, content=f"Rozszerzenie Home Assistant jest niedostępne — narzędzie '{name}' niedostępne.")

        if not await self.is_enabled():
            return PluginContribution(tools=[], entities=[], dispatch=_empty_dispatch)

        config = await self.get_config()
        if not config.base_url or not config.access_token:
            return PluginContribution(tools=[], entities=[], dispatch=_empty_dispatch)

        client = self._build_client(config)
        devices = await self.resolve_devices(client=client)

        group_instances = await self.list_groups()
        groups = [DeviceGroup(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids) for cfg in group_instances.values()]

        device_registry = DeviceRegistry(devices, groups)
        executor = HomeAssistantToolExecutor(device_registry, client)

        entities: list[EntitySpec] = [
            EntitySpec(
                id=device.id,
                name=device.name,
                capabilities=frozenset(
                    EntityCapability(tool_name=name, features=features) for name, features in device.capabilities.items()
                ),
            )
            for device in devices
        ]
        entities.extend(
            EntitySpec(id=group.id, name=group.name, capabilities=_GROUP_CAPABILITIES) for group in groups
        )

        async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            try:
                return await executor.execute(name, arguments)
            except Exception as e:
                logger.error(f"Błąd podczas wykonania narzędzia [{name}]: {e}")
                return ToolResult(is_error=True, content=f"Błąd wykonania narzędzia '{name}': {e}")

        return PluginContribution(tools=build_tool_definitions(), entities=entities, dispatch=dispatch)
