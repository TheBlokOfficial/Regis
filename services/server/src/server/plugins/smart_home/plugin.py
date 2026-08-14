"""SmartHomePlugin — implementacja `PluginProvider` (Warstwa 1) dla domeny smart home.

Jedyny byt widoczny dla Gateway w tej domenie (wizja, sekcja 2, "Plugin").
Wewnątrz orkiestruje jedną lub więcej instancji integracji (dziś: Home
Assistant) i w pełni rozwiązuje grupy urządzeń — obie te rzeczy przestają
być widoczne na zewnątrz pluginu.

Architektura wzorowana na `BackendRegistry`/`PromptStore` — instancje jako
pliki JSON w `data/plugins/smart_home/{integrations,groups}/*.json`. W
przeciwieństwie do dostawców LLM, integracji może być jednocześnie włączonych
wiele naraz — stąd pole `enabled` per instancja zamiast pojęcia jednego
"aktywnego" backendu.

Plugin nie zna z góry żadnej konkretnej integracji (np. Home Assistant) —
integracje rejestrują swój typ jawnie przez `register_integration_type()`,
wywoływane z `main.py` (kompozycja aplikacji) przy starcie.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from shared import (
    get_logger,
    get_service_root,
    sanitize_identifier,
    ConfigStore,
    ProviderMetadataResponse,
    ProviderTypeSpecDTO,
)

from server.agent.backend import ToolResult
from server.agent.context_provider_contract import Fact
from server.agent.plugin_contract import EntityCapability, EntitySpec, PluginContribution
from server.plugins.smart_home.contract import DeviceIntegration
from server.plugins.smart_home.models import (
    Device,
    DeviceGroup,
    DeviceGroupFileContent,
    DeviceGroupInstanceConfig,
    IntegrationFileContent,
    IntegrationInstanceConfig,
)
from server.plugins.smart_home.registry import DeviceRegistry
from server.plugins.smart_home.tools import SmartHomeToolExecutor, TOOL_NAMES, build_tool_definitions

logger = get_logger("regis.plugins.smart_home")

IntegrationFactoryFn = Callable[[Dict[str, Any]], DeviceIntegration]

# Grupa jest z zewnątrz nieodróżnialna od pojedynczego urządzenia (wizja,
# sekcja 4.4) — deklaruje więc zawsze wszystkie narzędzia rdzenia; gating
# per-członek następuje dopiero przy wykonaniu (patrz `tools.py`).
_GROUP_CAPABILITIES = frozenset(EntityCapability(tool_name=name) for name in TOOL_NAMES)


class SmartHomePlugin:
    """Plugin Smart Home — spełnia kontrakt `PluginProvider` Gateway.

    Nie dziedziczy jawnie po `PluginProvider` (Protocol strukturalny) —
    pasuje kształtem dzięki polu `plugin_id` i metodzie `build()`.
    """

    plugin_id = "smart_home"

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data" / "plugins" / "smart_home")).resolve()
        self.integrations_dir = self.base_data_dir / "integrations"
        self.groups_dir = self.base_data_dir / "groups"
        self._lock = asyncio.Lock()
        self._defaults_ensured = False
        self._registered_types: Dict[str, tuple[IntegrationFactoryFn, ProviderTypeSpecDTO]] = {}

    async def _ensure_defaults(self) -> None:
        """Tworzy katalogi danych jeśli nie istnieją. Plugin startuje bez integracji i grup."""
        if self._defaults_ensured:
            return
        async with self._lock:
            if self._defaults_ensured:
                return
            self.integrations_dir.mkdir(parents=True, exist_ok=True)
            self.groups_dir.mkdir(parents=True, exist_ok=True)
            self._defaults_ensured = True

    # --------------------------------------------------------------------------
    # Rejestracja typów integracji (wywoływana jawnie z main.py przy starcie)
    # --------------------------------------------------------------------------

    def register_integration_type(
        self,
        type_name: str,
        factory: IntegrationFactoryFn,
        schema: ProviderTypeSpecDTO,
    ) -> None:
        """Rejestruje typ integracji dostępny do tworzenia instancji.

        Wołane jawnie przez kompozycję aplikacji (`main.py`), nigdy przez sam
        plugin — to integracja się rejestruje, nie plugin jej szuka.
        """
        if type_name in self._registered_types:
            logger.warning(f"Typ integracji [{type_name}] rejestrowany ponownie — nadpisuję poprzednią rejestrację.")
        self._registered_types[type_name] = (factory, schema)
        logger.info(f"Zarejestrowano typ integracji: [{type_name}]")

    def get_all_schemas(self) -> ProviderMetadataResponse:
        """Zwraca schematy opcji konfiguracyjnych wszystkich zarejestrowanych typów integracji."""
        return ProviderMetadataResponse(provider_types=[schema for _, schema in self._registered_types.values()])

    def _instantiate_integration(self, config: IntegrationInstanceConfig) -> DeviceIntegration:
        """Tworzy instancję integracji przez wcześniej zarejestrowaną fabrykę."""
        registration = self._registered_types.get(config.type)
        if registration is None:
            raise ValueError(f"Nieznany lub niezarejestrowany typ integracji: '{config.type}'.")
        factory, _ = registration
        logger.info(f"Tworzenie instancji integracji '{config.name}' [ID: {config.id}, Typ: {config.type}]...")
        return factory(config.options)

    # --------------------------------------------------------------------------
    # CRUD instancji integracji
    # --------------------------------------------------------------------------

    async def create_integration_instance(
        self,
        provider_type: str,
        name: str,
        options: Dict[str, Any],
        enabled: bool = True,
        custom_id: Optional[str] = None,
    ) -> IntegrationInstanceConfig:
        """Tworzy nową skonfigurowaną instancję integracji i zapisuje ją w pliku JSON.

        :raises ValueError: jeśli `provider_type` nie jest zarejestrowanym typem integracji.
        """
        await self._ensure_defaults()
        if provider_type not in self._registered_types:
            supported = ", ".join(sorted(self._registered_types.keys())) or "(brak zarejestrowanych typów)"
            raise ValueError(f"Niewspierany typ integracji: '{provider_type}'. Dozwolone: {supported}.")

        instance_id = custom_id or f"int_{uuid.uuid4().hex[:8]}"
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        content = IntegrationFileContent(type=provider_type, name=name, options=options, enabled=enabled)
        file_path = self.integrations_dir / f"{instance_id}.json"

        async with self._lock:
            await asyncio.to_thread(ConfigStore(IntegrationFileContent, file_path).save, content)

        logger.info(f"Utworzono nową instancję integracji [{name}] z ID: {instance_id}")
        return IntegrationInstanceConfig(id=instance_id, **content.model_dump())

    async def list_integration_instances(self) -> Dict[str, IntegrationInstanceConfig]:
        """Wczytuje i zwraca słownik wszystkich zadeklarowanych instancji integracji {id: config}."""
        await self._ensure_defaults()
        instances: Dict[str, IntegrationInstanceConfig] = {}

        async with self._lock:
            for file_path in sorted(self.integrations_dir.glob("*.json")):
                try:
                    instance_id = file_path.stem
                    content = await asyncio.to_thread(ConfigStore(IntegrationFileContent, file_path).load)
                    instances[instance_id] = IntegrationInstanceConfig(id=instance_id, **content.model_dump())
                except Exception as e:
                    logger.error(f"Błąd podczas wczytywania pliku instancji integracji [{file_path}]: {e}")

        return instances

    async def update_integration_instance(
        self,
        provider_id: str,
        name: str | None = None,
        options: Dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> IntegrationInstanceConfig:
        """Aktualizuje wybrane pola istniejącej instancji integracji. Rzuca ValueError jeśli nie istnieje."""
        sanitize_identifier(provider_id, field_name="provider_id")
        await self._ensure_defaults()
        file_path = self.integrations_dir / f"{provider_id}.json"
        if not file_path.exists():
            raise ValueError(f"Integracja o ID '{provider_id}' nie istnieje.")

        async with self._lock:
            existing = await asyncio.to_thread(ConfigStore(IntegrationFileContent, file_path).load)
            updated = IntegrationFileContent(
                type=existing.type,
                name=name if name is not None else existing.name,
                options=options if options is not None else existing.options,
                enabled=enabled if enabled is not None else existing.enabled,
            )
            await asyncio.to_thread(ConfigStore(IntegrationFileContent, file_path).save, updated)

        logger.info(f"Zaktualizowano instancję integracji [{provider_id}].")
        return IntegrationInstanceConfig(id=provider_id, **updated.model_dump())

    async def delete_integration_instance(self, provider_id: str) -> bool:
        """Usuwa plik instancji integracji z dysku."""
        sanitize_identifier(provider_id, field_name="provider_id")
        await self._ensure_defaults()
        async with self._lock:
            file_path = self.integrations_dir / f"{provider_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Usunięto instancję integracji [{provider_id}] z dysku.")
                return True
            return False

    # --------------------------------------------------------------------------
    # CRUD grup urządzeń — prywatna, plugin-wide konfiguracja (wizja, sekcja 4.4)
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

    async def list_groups(self) -> Dict[str, DeviceGroupInstanceConfig]:
        """Wczytuje i zwraca słownik wszystkich zadeklarowanych grup {id: config}."""
        await self._ensure_defaults()
        instances: Dict[str, DeviceGroupInstanceConfig] = {}

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
    # PluginProvider — budowanie wkładu na czas jednej interakcji agenta
    # --------------------------------------------------------------------------

    async def build(self, facts: list[Fact]) -> PluginContribution:
        """Buduje pełny, spłaszczony wkład pluginu na czas jednej interakcji agenta.

        Instancjonuje włączone integracje (przez zarejestrowane fabryki),
        agreguje ich urządzenia i skonfigurowane grupy w jeden `DeviceRegistry`
        wewnętrzny na tę turę, tworzy narzędzia rdzenia (`get_state`/`turn_on`/
        `turn_off`) i encje (z już rozwiązanymi grupami) dla Gateway.

        :param facts: Fakty zebrane w tej turze przez Gateway — nieużywane w
            tej iteracji (żaden dzisiejszy przypadek użycia tego nie wymaga),
            przyjmowane jako część kontraktu na przyszłość.
        """
        del facts  # nieużywane w tej iteracji — patrz docstring

        all_instances = await self.list_integration_instances()
        enabled_instances = [cfg for cfg in all_instances.values() if cfg.enabled]

        integrations: dict[str, DeviceIntegration] = {}
        for cfg in enabled_instances:
            try:
                integrations[cfg.id] = self._instantiate_integration(cfg)
            except Exception as e:
                logger.error(f"Nie udało się zainicjalizować integracji [{cfg.id}]: {e}")

        devices: list[Device] = []
        for provider_id, integration in integrations.items():
            try:
                raw_devices = await integration.list_devices()
            except Exception as e:
                logger.error(f"Nie udało się pobrać urządzeń z integracji [{provider_id}]: {e}")
                continue
            # Nadajemy urządzeniom przestrzeń nazw integracji, by ref pozostawały
            # unikalne w DeviceRegistry nawet przy wielu jednocześnie włączonych instancjach.
            for device in raw_devices:
                device.integration_id = provider_id
                device.id = f"{provider_id}:{device.id}"
            devices.extend(raw_devices)

        group_instances = await self.list_groups()
        groups = [DeviceGroup(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids) for cfg in group_instances.values()]

        device_registry = DeviceRegistry(devices, groups)
        executor = SmartHomeToolExecutor(device_registry, integrations)

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
