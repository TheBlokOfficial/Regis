"""HomeAssistantExtension — jedyny byt widoczny dla Gateway w tej domenie.

Spełnia strukturalnie `PluginProvider` (`agent/plugin_contract.py`) i
`NetworkExtension` (`network/extension_contract.py`) — jeden identyfikator
(`plugin_id == extension_id == "home_assistant"`) na obu granicach, plus
opcjonalnie na trzeciej: kluczu rejestru widoków frontendu.

W przeciwieństwie do dawnego `SmartHomePlugin` + `integrations/home_assistant.py`
nie ma tu żadnej dynamicznej rejestracji typów integracji — Home Assistant
jest jedynym, znanym z góry backendem tego rozszerzenia. Wielość instancji
(kilka jednoczesnych połączeń HA) zostaje — to inna oś niż polimorfizm typu
integracji.
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
    Device,
    DeviceDeclarationFileContent,
    DeviceGroup,
    DeviceGroupFileContent,
    DeviceGroupInstanceConfig,
    HAConnectionConfig,
    HAConnectionFileContent,
)
from server.extensions.home_assistant.registry import DeviceRegistry
from server.extensions.home_assistant.routes import create_home_assistant_router
from server.extensions.home_assistant.tools import HomeAssistantToolExecutor, build_tool_definitions, TOOL_NAMES

logger = get_logger("regis.extensions.home_assistant")

ClientFactoryFn = Callable[[HAConnectionConfig], HomeAssistantClient]

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
        self.connections_dir = self.base_data_dir / "connections"
        self.groups_dir = self.base_data_dir / "groups"
        self.declarations_dir = self.base_data_dir / "declarations"
        self.state_path = self.base_data_dir / "state.json"
        self._lock = asyncio.Lock()
        self._defaults_ensured = False
        self._client_factory = client_factory

    async def _ensure_defaults(self) -> None:
        """Tworzy katalogi danych jeśli nie istnieją. Rozszerzenie startuje bez połączeń i grup."""
        if self._defaults_ensured:
            return
        async with self._lock:
            if self._defaults_ensured:
                return
            self.connections_dir.mkdir(parents=True, exist_ok=True)
            self.groups_dir.mkdir(parents=True, exist_ok=True)
            self.declarations_dir.mkdir(parents=True, exist_ok=True)
            self._defaults_ensured = True

    def _build_client(self, config: HAConnectionConfig) -> HomeAssistantClient:
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
    # CRUD połączeń
    # --------------------------------------------------------------------------

    async def create_connection(
        self,
        name: str,
        base_url: str,
        access_token: str,
        enabled: bool = True,
        custom_id: Optional[str] = None,
    ) -> HAConnectionConfig:
        """Tworzy nowe skonfigurowane połączenie Home Assistant i zapisuje je w pliku JSON."""
        await self._ensure_defaults()
        connection_id = custom_id or f"con_{uuid.uuid4().hex[:8]}"
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        content = HAConnectionFileContent(name=name, base_url=base_url, access_token=access_token, enabled=enabled)
        file_path = self.connections_dir / f"{connection_id}.json"

        async with self._lock:
            await asyncio.to_thread(ConfigStore(HAConnectionFileContent, file_path).save, content)

        logger.info(f"Utworzono nowe połączenie Home Assistant [{name}] z ID: {connection_id}")
        return HAConnectionConfig(id=connection_id, **content.model_dump())

    async def list_connections(self) -> dict[str, HAConnectionConfig]:
        """Wczytuje i zwraca słownik wszystkich zadeklarowanych połączeń {id: config}."""
        await self._ensure_defaults()
        instances: dict[str, HAConnectionConfig] = {}

        async with self._lock:
            for file_path in sorted(self.connections_dir.glob("*.json")):
                try:
                    connection_id = file_path.stem
                    content = await asyncio.to_thread(ConfigStore(HAConnectionFileContent, file_path).load)
                    instances[connection_id] = HAConnectionConfig(id=connection_id, **content.model_dump())
                except Exception as e:
                    logger.error(f"Błąd podczas wczytywania pliku połączenia [{file_path}]: {e}")

        return instances

    async def update_connection(
        self,
        connection_id: str,
        name: str | None = None,
        base_url: str | None = None,
        access_token: str | None = None,
        enabled: bool | None = None,
    ) -> HAConnectionConfig:
        """Aktualizuje wybrane pola istniejącego połączenia. Rzuca ValueError jeśli nie istnieje."""
        sanitize_identifier(connection_id, field_name="connection_id")
        await self._ensure_defaults()
        file_path = self.connections_dir / f"{connection_id}.json"
        if not file_path.exists():
            raise ValueError(f"Połączenie o ID '{connection_id}' nie istnieje.")

        async with self._lock:
            existing = await asyncio.to_thread(ConfigStore(HAConnectionFileContent, file_path).load)
            updated = HAConnectionFileContent(
                name=name if name is not None else existing.name,
                base_url=base_url if base_url is not None else existing.base_url,
                access_token=access_token if access_token is not None else existing.access_token,
                enabled=enabled if enabled is not None else existing.enabled,
            )
            await asyncio.to_thread(ConfigStore(HAConnectionFileContent, file_path).save, updated)

        logger.info(f"Zaktualizowano połączenie [{connection_id}].")
        return HAConnectionConfig(id=connection_id, **updated.model_dump())

    async def delete_connection(self, connection_id: str) -> bool:
        """Usuwa plik połączenia z dysku."""
        sanitize_identifier(connection_id, field_name="connection_id")
        await self._ensure_defaults()
        async with self._lock:
            file_path = self.connections_dir / f"{connection_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Usunięto połączenie [{connection_id}] z dysku.")
                return True
            return False

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
    # Deklaracje widoczności katalogu — per połączenie
    # --------------------------------------------------------------------------

    async def get_declaration(self, connection_id: str) -> DeviceDeclarationFileContent:
        """Wczytuje deklarację widoczności katalogu połączenia. Brak pliku = wszystko widoczne."""
        await self._ensure_defaults()
        file_path = self.declarations_dir / f"{connection_id}.json"
        return await asyncio.to_thread(ConfigStore(DeviceDeclarationFileContent, file_path).load)

    async def save_declaration(self, connection_id: str, content: DeviceDeclarationFileContent) -> None:
        """Nadpisuje deklarację widoczności katalogu połączenia — pierwszy zapis z UI tworzy plik."""
        sanitize_identifier(connection_id, field_name="connection_id")
        await self._ensure_defaults()
        file_path = self.declarations_dir / f"{connection_id}.json"
        async with self._lock:
            await asyncio.to_thread(ConfigStore(DeviceDeclarationFileContent, file_path).save, content)
        logger.info(f"Zapisano deklarację katalogu dla połączenia [{connection_id}].")

    # --------------------------------------------------------------------------
    # Wspólna logika: katalog połączenia po zastosowaniu deklaracji
    # --------------------------------------------------------------------------

    async def resolve_devices(
        self, connection_id: str, config: HAConnectionConfig, client: HomeAssistantClient | None = None
    ) -> list[tuple[Device, bool]]:
        """Zwraca urządzenia połączenia (namespaced ID) sparowane z flagą `enabled` wg deklaracji.

        Współdzielone przez `build()` (filtruje `enabled=False`) i endpoint
        katalogu w `routes.py` (pokazuje wszystko, `enabled` jako stan checkboxa)
        — jedna logika merge, zero duplikacji.

        :param client: Opcjonalny, już zbudowany klient (np. ten sam, którego
            `build()` przekazuje dalej do wykonawcy narzędzi) — pozwala uniknąć
            tworzenia drugiej, nieużywanej instancji klienta dla tego samego
            połączenia w jednej turze. Gdy pominięty, budowany jest tu na miejscu
            (ścieżka REST katalogu nie ma z czym go współdzielić).
        """
        if client is None:
            client = self._build_client(config)
        try:
            raw_devices = await client.list_devices()
        except Exception as e:
            logger.error(f"Nie udało się pobrać urządzeń z połączenia [{connection_id}]: {e}")
            return []

        declaration = await self.get_declaration(connection_id)
        result: list[tuple[Device, bool]] = []
        for device in raw_devices:
            entry = declaration.entries.get(device.id)
            enabled = entry.enabled if entry is not None else True
            name = entry.display_name if entry is not None and entry.display_name else device.name
            namespaced = Device(
                id=f"{connection_id}:{device.id}",
                connection_id=connection_id,
                name=name,
                kind=device.kind,
                capabilities=device.capabilities,
                area=device.area,
            )
            result.append((namespaced, enabled))
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

        if not await self.is_enabled():
            async def _disabled_dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
                return ToolResult(is_error=True, content=f"Rozszerzenie Home Assistant jest wyłączone — narzędzie '{name}' niedostępne.")

            return PluginContribution(tools=[], entities=[], dispatch=_disabled_dispatch)

        all_connections = await self.list_connections()
        enabled_connections = [cfg for cfg in all_connections.values() if cfg.enabled]

        clients: dict[str, HomeAssistantClient] = {cfg.id: self._build_client(cfg) for cfg in enabled_connections}

        devices: list[Device] = []
        for cfg in enabled_connections:
            for device, enabled in await self.resolve_devices(cfg.id, cfg, client=clients[cfg.id]):
                if enabled:
                    devices.append(device)

        group_instances = await self.list_groups()
        groups = [DeviceGroup(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids) for cfg in group_instances.values()]

        device_registry = DeviceRegistry(devices, groups)
        executor = HomeAssistantToolExecutor(device_registry, clients)

        entities: list[EntitySpec] = [
            EntitySpec(
                id=device.id,
                name=device.name,
                capabilities=frozenset(EntityCapability(tool_name=cap) for cap in device.capabilities),
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
