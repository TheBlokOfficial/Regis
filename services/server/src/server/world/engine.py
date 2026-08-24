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
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from shared import ConfigStore, get_logger, get_service_root, sanitize_identifier

from server.agent.context_provider import ContextBuild
from server.agent.llm import ToolDefinition, ToolResult
from server.world.client import HomeAssistantClient
from server.world.models import (
    ClientCapability,
    DeclaredDeviceEntry,
    DeclaredDevicesFileContent,
    Device,
    DeviceGroup,
    DeviceGroupFileContent,
    DeviceGroupInstanceConfig,
    HomeAssistantConfig,
    RoomFileContent,
    RoomInstanceConfig,
    SenderProfile,
    SenderProfilesFileContent,
)
from server.world.prompt_sections import (
    CONDITION_SPECS_BY_KEY,
    PromptSection,
    PromptSectionsConfig,
    PromptSectionStore,
    TurnFacts,
    render_section,
)
from server.world.prompts import PromptInstanceConfig, WorldPromptStore
from server.world.registry import DeviceRegistry
from server.world.tools import TOOL_NAMES, HomeAssistantToolExecutor, build_tool_definitions

logger = get_logger("regis.world")

# Nazwy dni po polsku — `datetime.strftime("%A")` zależy od locale procesu, więc dawałoby
# raz "Monday", raz "poniedziałek", zależnie od maszyny.
_WEEKDAY_NAMES = ("poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela")

ClientFactoryFn = Callable[[HomeAssistantConfig], HomeAssistantClient]

_GET_TIME_TOOL = "get_time"
_SPEAK_IN_ROOM_TOOL = "speak_in_room"


class WorldEngine:
    """Jedyny silnik świata — konfiguracja Home Assistant (singleton), zadeklarowane
    urządzenia, grupy i przypisania nadawców do pokoi. Implementuje `WorldInterface`."""

    def __init__(self, data_dir: Optional[Path] = None, client_factory: Optional[ClientFactoryFn] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data" / "world")).resolve()
        self.groups_dir = self.base_data_dir / "groups"
        self.rooms_dir = self.base_data_dir / "rooms"
        self.config_path = self.base_data_dir / "config.json"
        self.declared_devices_path = self.base_data_dir / "declared_devices.json"
        self.senders_path = self.base_data_dir / "senders.json"
        self._lock = asyncio.Lock()
        self._defaults_ensured = False
        self._client_factory = client_factory
        # World jest jedynym autorem promptu tej tury, gdy podłączony — własny magazyn
        # profili tożsamości (do 3, przełączalne), zarządzany wewnętrznie (patrz `build()`).
        self._prompt_store = WorldPromptStore(self.base_data_dir)
        self._section_store = PromptSectionStore(self.base_data_dir)

    async def _ensure_defaults(self) -> None:
        """Tworzy katalogi grup/pokoi jeśli nie istnieją. Silnik startuje bez konfiguracji i grup."""
        if self._defaults_ensured:
            return
        async with self._lock:
            if self._defaults_ensured:
                return
            self.groups_dir.mkdir(parents=True, exist_ok=True)
            self.rooms_dir.mkdir(parents=True, exist_ok=True)
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

    async def save_config(self, base_url: str, access_token: str | None = None) -> HomeAssistantConfig:
        """Zapisuje adres serwera i (opcjonalnie) token dostępu.

        Backend, nie frontend, jest jedynym bezpiecznym miejscem na regułę
        "brak tokenu w żądaniu = zachowaj obecny" — GET /config zawsze zwraca
        token zamaskowany (`_mask_token`), więc frontend nigdy nie zna
        prawdziwej wartości i nie może jej sam odesłać z powrotem.
        """
        await self._ensure_defaults()
        token = access_token
        if not token:
            current = await asyncio.to_thread(ConfigStore(HomeAssistantConfig, self.config_path).load)
            token = current.access_token
        content = HomeAssistantConfig(base_url=base_url, access_token=token)
        async with self._lock:
            await asyncio.to_thread(ConfigStore(HomeAssistantConfig, self.config_path).save, content)
        logger.info("Zaktualizowano konfigurację Home Assistant.")
        return content

    async def test_connection(self, base_url: str, access_token: str | None = None) -> tuple[bool, str]:
        """Testuje połączenie z Home Assistant bez zapisywania konfiguracji.

        Brak tokenu w żądaniu = użyj obecnie zapisanego (test samego adresu
        bez konieczności ponownego wklejania tokenu).
        """
        if not base_url:
            return False, "Adres serwera jest wymagany."
        token = access_token
        if not token:
            current = await self.get_config()
            token = current.access_token
        if not token:
            return False, "Token dostępu jest wymagany."
        client = self._build_client(HomeAssistantConfig(base_url=base_url, access_token=token))
        return await client.test_connection()

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
    # CRUD pokoi — pełnoprawny byt World, niezależny od Home Assistant Areas
    # --------------------------------------------------------------------------

    async def create_room(self, name: str, custom_id: Optional[str] = None) -> RoomInstanceConfig:
        """Tworzy nowy pokój i zapisuje go w pliku JSON."""
        await self._ensure_defaults()
        room_id = custom_id or f"room_{uuid.uuid4().hex[:8]}"
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        content = RoomFileContent(name=name)
        file_path = self.rooms_dir / f"{room_id}.json"

        async with self._lock:
            await asyncio.to_thread(ConfigStore(RoomFileContent, file_path).save, content)

        logger.info(f"Utworzono nowy pokój [{name}] z ID: {room_id}")
        return RoomInstanceConfig(id=room_id, **content.model_dump())

    async def list_rooms(self) -> dict[str, RoomInstanceConfig]:
        """Wczytuje i zwraca słownik wszystkich pokoi {id: config}."""
        await self._ensure_defaults()
        instances: dict[str, RoomInstanceConfig] = {}

        async with self._lock:
            for file_path in sorted(self.rooms_dir.glob("*.json")):
                try:
                    room_id = file_path.stem
                    content = await asyncio.to_thread(ConfigStore(RoomFileContent, file_path).load)
                    instances[room_id] = RoomInstanceConfig(id=room_id, **content.model_dump())
                except Exception as e:
                    logger.error(f"Błąd podczas wczytywania pliku pokoju [{file_path}]: {e}")

        return instances

    async def update_room(self, room_id: str, name: str) -> RoomInstanceConfig:
        """Zmienia nazwę istniejącego pokoju. Rzuca ValueError jeśli nie istnieje."""
        sanitize_identifier(room_id, field_name="room_id")
        await self._ensure_defaults()
        file_path = self.rooms_dir / f"{room_id}.json"
        if not file_path.exists():
            raise ValueError(f"Pokój o ID '{room_id}' nie istnieje.")

        async with self._lock:
            updated = RoomFileContent(name=name)
            await asyncio.to_thread(ConfigStore(RoomFileContent, file_path).save, updated)

        logger.info(f"Zaktualizowano pokój [{room_id}].")
        return RoomInstanceConfig(id=room_id, **updated.model_dump())

    async def delete_room(self, room_id: str) -> bool:
        """Usuwa plik pokoju z dysku. Urządzenia/nadawcy wskazujący na usunięty `room_id`
        po prostu przestają mieć dopasowanie (cicho traktowani jak nieprzypisani,
        patrz `_render_devices_section`) — bez cascade delete."""
        sanitize_identifier(room_id, field_name="room_id")
        await self._ensure_defaults()
        async with self._lock:
            file_path = self.rooms_dir / f"{room_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Usunięto pokój [{room_id}] z dysku.")
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

    async def add_declared_device(
        self, entity_id: str, display_name: str | None = None, room_id: str | None = None
    ) -> None:
        """Dodaje encję do zadeklarowanej listy (widoczna dla agenta od tej pory)."""
        current = await self.get_declared_devices()
        current.entries[entity_id] = DeclaredDeviceEntry(display_name=display_name, room_id=room_id)
        await self._save_declared_devices(current)
        logger.info(f"Zadeklarowano urządzenie [{entity_id}].")

    async def update_declared_device(
        self, entity_id: str, display_name: str | None, room_id: str | None = None
    ) -> DeclaredDeviceEntry:
        """Zmienia `display_name`/`room_id` istniejącego wpisu. Rzuca ValueError jeśli nie istnieje."""
        current = await self.get_declared_devices()
        if entity_id not in current.entries:
            raise ValueError(f"Urządzenie '{entity_id}' nie jest zadeklarowane.")
        current.entries[entity_id] = DeclaredDeviceEntry(display_name=display_name, room_id=room_id)
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
            result.append(
                Device(
                    id=entity_id,
                    name=name,
                    kind=raw.kind,
                    capabilities=raw.capabilities,
                    area=raw.area,
                    room_id=entry.room_id,
                )
            )
        return result

    # --------------------------------------------------------------------------
    # Przypisania nadawców do pokoi — sender_id -> pokój (zero wiedzy o kanale/urządzeniu)
    # --------------------------------------------------------------------------

    async def get_senders(self) -> SenderProfilesFileContent:
        """Wczytuje przypisania nadawców. Brak pliku = pusty rejestr."""
        await self._ensure_defaults()
        return await asyncio.to_thread(ConfigStore(SenderProfilesFileContent, self.senders_path).load)

    async def _save_senders(self, content: SenderProfilesFileContent) -> None:
        await self._ensure_defaults()
        async with self._lock:
            await asyncio.to_thread(ConfigStore(SenderProfilesFileContent, self.senders_path).save, content)

    async def register_sender(self, sender_id: str, profile: SenderProfile) -> SenderProfile:
        """Rejestruje lub nadpisuje przypisanie nadawcy do pokoju."""
        current = await self.get_senders()
        current.entries[sender_id] = profile
        await self._save_senders(current)
        logger.info(f"Przypisano nadawcę [{sender_id}] do pokoju.")
        return profile

    async def remove_sender(self, sender_id: str) -> bool:
        """Usuwa przypisanie nadawcy."""
        current = await self.get_senders()
        if sender_id not in current.entries:
            return False
        del current.entries[sender_id]
        await self._save_senders(current)
        logger.info(f"Usunięto przypisanie nadawcy [{sender_id}].")
        return True

    async def _find_speaker_by_room(self, room: str) -> tuple[str | None, list[str]]:
        """Szuka w podanym pokoju nadawcy zdolnego **odtworzyć mowę**, w dwóch krokach:
        nazwa -> `Room.id` (dopasowanie po `Room.name`, bez rozróżniania wielkości
        liter), potem `Room.id` -> `sender_id` (po `SenderProfile.room_id`).

        Kandydaci bez `ClientCapability.SPEAKER` są odrzucani — przekierowanie mowy na
        klienta czysto tekstowego (np. kartę przeglądarki przypisaną do tego pokoju)
        nie miałoby jak się odtworzyć, a wcześniej przechodziło bez żadnego sygnału.

        :return: `(sender_id, [])` przy jednoznacznym dopasowaniu, w przeciwnym razie
            `(None, kandydaci)` — pusta lista kandydatów oznacza brak pasującego pokoju
            albo brak w nim czegokolwiek z głośnikiem.
        """
        needle = room.strip().lower()
        rooms = await self.list_rooms()
        matching_room_ids = {room_id for room_id, cfg in rooms.items() if cfg.name.lower() == needle}
        if not matching_room_ids:
            return None, []

        senders = await self.get_senders()
        matches = [
            sid
            for sid, profile in senders.entries.items()
            if profile.room_id in matching_room_ids and ClientCapability.SPEAKER in profile.capabilities
        ]
        if len(matches) == 1:
            return matches[0], []
        return None, matches

    # --------------------------------------------------------------------------
    # Sekcje kontekstu tury — edytowalny tekst faktów wstrzykiwanych co turę
    # --------------------------------------------------------------------------

    async def get_prompt_sections(self) -> PromptSectionsConfig:
        return await self._section_store.load()

    async def save_prompt_sections(self, sections: list[PromptSection]) -> PromptSectionsConfig:
        """Podmienia całą uporządkowaną listę sekcji.

        :raises ValueError: gdy sekcja używa nieznanego warunku — cicho zapisana
            nigdy by się nie pojawiła, a użytkownik zobaczyłby "zapisano" i szukał
            błędu w treści promptu zamiast w konfiguracji.
        """
        unknown = {s.condition for s in sections} - set(CONDITION_SPECS_BY_KEY)
        if unknown:
            raise ValueError(f"Nieznane warunki sekcji: {', '.join(sorted(unknown))}.")
        config = PromptSectionsConfig(sections=sections)
        await self._section_store.save(config)
        return config

    async def reset_prompt_sections(self) -> PromptSectionsConfig:
        return await self._section_store.reset()

    # --------------------------------------------------------------------------
    # Profile promptu — tożsamość Świata, do 3 przełączalnych profili
    # --------------------------------------------------------------------------

    async def list_prompts(self) -> list[PromptInstanceConfig]:
        return await self._prompt_store.list_all()

    async def get_prompt(self, prompt_id: str) -> PromptInstanceConfig | None:
        return await self._prompt_store.get(prompt_id)

    async def create_prompt(
        self,
        name: str,
        content: str,
        description: str | None = None,
        custom_id: str | None = None,
        set_active: bool = False,
    ) -> PromptInstanceConfig:
        return await self._prompt_store.create(
            name=name, content=content, description=description, custom_id=custom_id, set_active=set_active
        )

    async def update_prompt(
        self, prompt_id: str, name: str | None = None, content: str | None = None, description: str | None = None
    ) -> PromptInstanceConfig:
        return await self._prompt_store.update(prompt_id, name=name, content=content, description=description)

    async def delete_prompt(self, prompt_id: str) -> bool:
        return await self._prompt_store.delete(prompt_id)

    async def get_active_prompt_id(self) -> str:
        return await self._prompt_store.get_active_id()

    async def set_active_prompt(self, prompt_id: str) -> None:
        await self._prompt_store.set_active(prompt_id)

    # --------------------------------------------------------------------------
    # WorldInterface — budowanie wkładu na czas jednej interakcji agenta
    # --------------------------------------------------------------------------

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        # Prompt tury dzieli się wzdłuż osi ZMIENNOŚCI, nie tematu (patrz
        # `agent/context_provider.py::ContextBuild`):
        #   * tożsamość (aktywny profil) -> `system_prompt`, stabilne między turami,
        #   * wszystko poniżej -> `turn_context`, prawdziwe tylko teraz.
        # Wcześniej było to jednym sklejonym stringiem, przez co znacznik czasu
        # zmieniał wiadomość zerową co turę, a tekstu faktów nie dało się edytować
        # bez dotykania tożsamości.
        # 1. Profil nadawcy: gdzie stoi i co potrafi. Modalność wyprowadzana jest tu,
        #    z trwałych `capabilities` klienta — nie przenoszona przez kernel jako flaga
        #    wywołania (dawne `voice_mode`), bo "ten klient ma głośnik" to fakt o rzeczy
        #    w świecie, dokładnie jak `Device.capabilities`.
        rooms_by_id = await self.list_rooms()
        profile: SenderProfile | None = None
        if sender_id is not None:
            senders = await self.get_senders()
            profile = senders.entries.get(sender_id)
        current_room = rooms_by_id.get(profile.room_id) if (profile and profile.room_id) else None

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

        device_list = (
            self._render_devices_section(
                devices,
                groups,
                rooms_by_id=rooms_by_id,
                current_room_id=current_room.id if current_room else None,
            )
            if (devices or groups)
            else None
        )
        # Sam pokój nadawcy, bez nagłówków i bez grup — pozwala napisać sekcję w rodzaju
        # "masz pod ręką: {urządzenia_w_pokoju}", nie zalewając promptu całym domem.
        room_devices = [d for d in devices if current_room is not None and d.room_id == current_room.id]
        room_device_list = (
            "\n".join(
                f"- [{d.id}] {d.name} (możliwości: {_format_capabilities(d)})" for d in room_devices
            )
            if room_devices
            else None
        )

        # 3. Fakty tury -> sekcje. Silnik dostarcza WYŁĄCZNIE dane; o tym, które
        #    bloki tekstu się pojawią i w jakiej kolejności, decyduje konfiguracja
        #    użytkownika (`prompt_sections.py`). Warunki są ewaluowane w Pythonie,
        #    więc użytkownik ich wybiera, a nie pisze — patrz docstring tamtego modułu.
        now = datetime.now()
        facts = TurnFacts(
            now=now.strftime("%Y-%m-%d %H:%M:%S"),
            date=now.strftime("%Y-%m-%d"),
            clock=now.strftime("%H:%M"),
            weekday=_WEEKDAY_NAMES[now.weekday()],
            capabilities=frozenset(c.value for c in profile.capabilities) if profile else frozenset(),
            room_id=current_room.id if current_room else None,
            room_name=current_room.name if current_room else None,
            client_name=profile.display_name if profile else None,
            device_list=device_list,
            room_device_list=room_device_list,
            room_names=tuple(room.name for room in rooms_by_id.values()),
            group_names=tuple(group.name for group in groups),
            ha_configured=bool(config.base_url and config.access_token),
        )
        sections = await self._section_store.load()
        context_parts = [
            rendered for section in sections.sections if (rendered := render_section(section, facts)) is not None
        ]

        # 4. Narzędzia + dispatch
        tool_definitions: list[ToolDefinition] = [
            ToolDefinition(
                name=_GET_TIME_TOOL,
                description="Zwraca aktualną datę i godzinę.",
                parameters={"type": "object", "properties": {}},
            ),
            ToolDefinition(
                name=_SPEAK_IN_ROOM_TOOL,
                description=(
                    "Przełącza dalszą część TEJ odpowiedzi na odbiornik przypisany do podanego pokoju "
                    "(np. przekierowanie mowy na inny głośnik). Użyj gdy użytkownik prosi o ogłoszenie/"
                    "odpowiedź w innym pokoju niż ten, z którego przyszło pytanie."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "room": {
                            "type": "string",
                            "description": "Nazwa pokoju — ta sama etykieta co w nagłówkach listy urządzeń/lokalizacji.",
                        }
                    },
                    "required": ["room"],
                },
            ),
        ]
        executor: HomeAssistantToolExecutor | None = None
        if devices or groups:
            tool_definitions.extend(build_tool_definitions())
            device_registry = DeviceRegistry(devices, groups)
            executor = HomeAssistantToolExecutor(device_registry, client) if client is not None else None

        async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            if name == _GET_TIME_TOOL:
                return ToolResult(content=facts.now)
            if name == _SPEAK_IN_ROOM_TOOL:
                room = str(arguments.get("room", ""))
                target_sender_id, candidates = await self._find_speaker_by_room(room)
                if target_sender_id is None:
                    if candidates:
                        return ToolResult(
                            is_error=True,
                            content=f"W pokoju '{room}' jest zarejestrowanych wielu odbiorników — nie można jednoznacznie wybrać.",
                        )
                    return ToolResult(is_error=True, content=f"Brak odbiornika z głośnikiem w pokoju '{room}'.")
                target_profile = (await self.get_senders()).entries.get(target_sender_id)
                target_room = (await self.list_rooms()).get(target_profile.room_id) if target_profile and target_profile.room_id else None
                target_room_name = target_room.name if target_room else None
                # Treść wyniku niesie NOWE ramowanie dostawy — cel zmienił się w połowie
                # tury, a kontekst tury powstał przed jej startem i już tego nie nadgoni.
                # Wyniki narzędzi wracają do modelu w pętli ReAct, więc to naturalny
                # kanał na tę korektę.
                #
                # Nie hardkodujemy tu zdania: przeliczamy sekcje użytkownika dla NOWEGO
                # celu i dokładamy tylko te, które wcześniej nie obowiązywały. Dzięki
                # temu tekst pochodzi z tej samej konfiguracji co start tury, a model
                # nie dostaje po raz drugi rzeczy, które już wie (np. listy urządzeń).
                content = f"Przełączono dalszą odpowiedź na pokój '{room}'."
                added = _sections_gained_after_redirect(sections, facts, target_profile, target_room_name)
                if added:
                    content = "\n\n".join([content, *added])
                return ToolResult(content=content, redirect_sender_id=target_sender_id)
            if executor is not None:
                try:
                    return await executor.execute(name, arguments)
                except Exception as e:
                    logger.error(f"Błąd podczas wykonania narzędzia [{name}]: {e}")
                    return ToolResult(is_error=True, content=f"Błąd wykonania narzędzia '{name}': {e}")
            return ToolResult(is_error=True, content=f"Nieznane narzędzie: '{name}'.")

        active_profile_content = await self._prompt_store.get_active_content()
        return ContextBuild(
            tool_definitions=tool_definitions,
            system_prompt=active_profile_content or None,
            turn_context="\n\n".join(context_parts) if context_parts else None,
            dispatch=dispatch,
        )

    @staticmethod
    def _render_devices_section(
        devices: list[Device],
        groups: list[DeviceGroup],
        rooms_by_id: dict[str, RoomInstanceConfig],
        current_room_id: str | None,
    ) -> str:
        """Renderuje SAMĄ listę urządzeń posegregowaną wg `Device.room_id` (pełnoprawny
        pokój World, niezależny od Home Assistant) — pełna adresowalność zawsze
        zachowana, segregacja to wyłącznie prezentacja. Urządzenie wskazujące na
        usunięty/nieznany `room_id` traktowane jest jak nieprzypisane (bez cascade
        delete przy usuwaniu pokoju).

        **Bez zdania wprowadzającego** — to należy do edytowalnej sekcji `devices`
        (`prompt_sections.py`), która wstawia tę listę w miejsce `{lista_urządzeń}`.
        Trzymanie nagłówka w obu miejscach dawało go w prompcie dwukrotnie."""
        by_room: dict[str, list[Device]] = {}
        unassigned: list[Device] = []
        for device in devices:
            if device.room_id and device.room_id in rooms_by_id:
                by_room.setdefault(device.room_id, []).append(device)
            else:
                unassigned.append(device)

        lines: list[str] = []
        for room_id, room_devices in sorted(by_room.items(), key=lambda item: item[0] != current_room_id):
            is_current = room_id == current_room_id
            header = f"### {rooms_by_id[room_id].name}" + (" (Twoja lokalizacja)" if is_current else "")
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


def _sections_gained_after_redirect(
    sections: PromptSectionsConfig,
    original: TurnFacts,
    target_profile: SenderProfile | None,
    target_room_name: str | None,
) -> list[str]:
    """Sekcje, które zaczynają obowiązywać dopiero po przekierowaniu na inny cel.

    Zwracamy RÓŻNICĘ, nie cały kontekst: model dostał już fakty tej tury na starcie,
    więc powtarzanie ich (zwłaszcza listy urządzeń) tylko zaśmiecałoby pętlę ReAct.
    Interesuje nas wyłącznie to, co się zmieniło — typowo ramowanie dostawy, bo cel
    ma głośnik, a pierwotny nadawca mógł go nie mieć.
    """
    # Zmienia się WYŁĄCZNIE to, co zależy od celu (możliwości, pokój, nazwa); reszta
    # faktów tej tury zostaje — stąd `replace` na istniejącym obiekcie zamiast budowania
    # go od zera, przy którym każde nowe pole `TurnFacts` trzeba by pamiętać tu przepisać.
    target_facts = replace(
        original,
        capabilities=frozenset(c.value for c in target_profile.capabilities) if target_profile else frozenset(),
        room_id=target_profile.room_id if target_profile else None,
        room_name=target_room_name,
        client_name=target_profile.display_name if target_profile else None,
    )
    gained: list[str] = []
    for section in sections.sections:
        # Porównujemy WYRENDEROWANY tekst, nie sam fakt "czy warunek zachodzi": po
        # rozdzieleniu na dwie gałęzie sekcja obowiązuje praktycznie zawsze, a realną
        # zmianą jest to, że mówi teraz co innego niż mówiła przed przekierowaniem.
        rendered = render_section(section, target_facts)
        if rendered and rendered != render_section(section, original):
            gained.append(rendered)
    return gained
