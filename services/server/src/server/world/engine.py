"""WorldEngine — jedyne ramię agenta dotykające świata zewnętrznego.

Implementuje `server.agent.context_provider.WorldInterface` strukturalnie
(bez importu — kernel nigdy nie importuje `server.world`, tylko odwrotnie).
Wewnątrz woła wprost swoje własne backendy (klient Home Assistant, magazyny
plikowe) — zero protokołu między nimi, bo to jeden, konkretny silnik, nie
generyczna kolekcja wymiennych rozszerzeń.

Sam silnik jest dziś **fasadą i orkiestratorem**; rzeczy, które robi, mieszkają
osobno i dają się testować bez niego:

* `stores.py` / `shared.JsonInstanceRepository` — trwałość (pliki JSON),
* `turn_context.py` — zamiana stanu na tekst tury (fakty, lista urządzeń),
* `tools/` — narzędzia agenta (definicje + wykonanie),
* `prompt_sections.py` / `prompts.py` — edytowalna treść i tożsamość.

Kolejność w `build()` jest świadoma: profil klienta (lokalizacja, możliwości)
liczony jest niezależnie od dostępności Home Assistant — brak/nieosiągalność
configu ucina wyłącznie encje/narzędzia HA, nigdy ramowanie dostawy.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from shared import JsonInstanceRepository, get_logger, get_service_root

from server.agent.context_provider import ContextBuild
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
)
from server.world.prompts import PromptInstanceConfig, WorldPromptStore
from server.world.registry import DeviceRegistry
from server.world.stores import DeclaredDevicesStore, HomeAssistantConfigStore, SenderProfilesStore
from server.world.tools import HomeAssistantToolExecutor, ToolSet, build_tool_definitions, get_time_tool, speak_in_room_tool
from server.world.turn_context import build_turn_facts, render_turn_context

logger = get_logger("regis.world")

ClientFactoryFn = Callable[[HomeAssistantConfig], HomeAssistantClient]


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
        # Grupy i pokoje to dwie kolekcje "plik na instancję" o identycznej mechanice —
        # dzielą lock silnika, żeby zapisy w obrębie jednego `WorldEngine` pozostały
        # serializowane dokładnie tak, jak przed wydzieleniem repozytorium.
        self._groups: JsonInstanceRepository[DeviceGroupFileContent] = JsonInstanceRepository(
            directory=self.groups_dir,
            content_cls=DeviceGroupFileContent,
            id_prefix="grp",
            label="grupę urządzeń",
            lock=self._lock,
        )
        self._rooms: JsonInstanceRepository[RoomFileContent] = JsonInstanceRepository(
            directory=self.rooms_dir,
            content_cls=RoomFileContent,
            id_prefix="room",
            label="pokój",
            lock=self._lock,
        )
        # Trzy byty trzymane w pojedynczych plikach (patrz `stores.py`) — dzielą ten sam
        # lock co kolekcje wyżej, więc zapisy w obrębie jednego silnika pozostają
        # serializowane dokładnie tak, jak przed wydzieleniem magazynów.
        self._config_store = HomeAssistantConfigStore(self.config_path, self._lock)
        self._declared_store = DeclaredDevicesStore(self.declared_devices_path, self._lock)
        self._senders_store = SenderProfilesStore(self.senders_path, self._lock)
        # World jest jedynym autorem promptu tej tury, gdy podłączony — własny magazyn
        # profili tożsamości (do 3, przełączalne), zarządzany wewnętrznie (patrz `build()`).
        self._prompt_store = WorldPromptStore(self.base_data_dir)
        self._section_store = PromptSectionStore(self.base_data_dir)

    async def _ensure_defaults(self) -> None:
        """Tworzy katalogi grup/pokoi jeśli nie istnieją. Silnik startuje bez konfiguracji i grup."""
        if self._defaults_ensured:
            return
        await self._groups.ensure_directory()
        await self._rooms.ensure_directory()
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
        return await self._config_store.load()

    async def save_config(self, base_url: str, access_token: str | None = None) -> HomeAssistantConfig:
        """Zapisuje adres serwera i (opcjonalnie) token dostępu.

        Backend, nie frontend, jest jedynym bezpiecznym miejscem na regułę
        "brak tokenu w żądaniu = zachowaj obecny" — GET /config zawsze zwraca
        token zamaskowany (`_mask_token`), więc frontend nigdy nie zna
        prawdziwej wartości i nie może jej sam odesłać z powrotem.
        """
        await self._ensure_defaults()
        token = access_token or (await self._config_store.load()).access_token
        content = HomeAssistantConfig(base_url=base_url, access_token=token)
        await self._config_store.save(content)
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
    # CRUD grup urządzeń i pokoi — dwie kolekcje "plik na instancję" o identycznej
    # mechanice, obsłużone tym samym `JsonInstanceRepository` (patrz `__init__`).
    # Metody poniżej są cienkimi fasadami: dokładają wyłącznie to, czego magazyn
    # nie wie — kształt DTO instancji i regułę "aktualizacja częściowa".
    # --------------------------------------------------------------------------

    async def create_group(
        self,
        name: str,
        device_ids: list[str],
        custom_id: Optional[str] = None,
    ) -> DeviceGroupInstanceConfig:
        """Tworzy nową grupę urządzeń i zapisuje ją w pliku JSON."""
        await self._ensure_defaults()
        content = DeviceGroupFileContent(name=name, device_ids=device_ids)
        group_id = await self._groups.create(content, custom_id=custom_id)
        return DeviceGroupInstanceConfig(id=group_id, **content.model_dump())

    async def list_groups(self) -> dict[str, DeviceGroupInstanceConfig]:
        """Wczytuje i zwraca słownik wszystkich zadeklarowanych grup {id: config}."""
        await self._ensure_defaults()
        return {
            gid: DeviceGroupInstanceConfig(id=gid, **content.model_dump())
            for gid, content in (await self._groups.load_all()).items()
        }

    async def update_group(
        self,
        group_id: str,
        name: str | None = None,
        device_ids: list[str] | None = None,
    ) -> DeviceGroupInstanceConfig:
        """Aktualizuje wybrane pola istniejącej grupy. Rzuca ValueError jeśli nie istnieje."""
        await self._ensure_defaults()
        existing = await self._groups.load(group_id)
        if existing is None:
            raise ValueError(f"Grupa o ID '{group_id}' nie istnieje.")
        updated = DeviceGroupFileContent(
            name=name if name is not None else existing.name,
            device_ids=device_ids if device_ids is not None else existing.device_ids,
        )
        await self._groups.save(group_id, updated)
        logger.info(f"Zaktualizowano grupę [{group_id}].")
        return DeviceGroupInstanceConfig(id=group_id, **updated.model_dump())

    async def delete_group(self, group_id: str) -> bool:
        """Usuwa plik grupy z dysku."""
        await self._ensure_defaults()
        return await self._groups.delete(group_id)

    async def create_room(self, name: str, custom_id: Optional[str] = None) -> RoomInstanceConfig:
        """Tworzy nowy pokój i zapisuje go w pliku JSON."""
        await self._ensure_defaults()
        content = RoomFileContent(name=name)
        room_id = await self._rooms.create(content, custom_id=custom_id)
        return RoomInstanceConfig(id=room_id, **content.model_dump())

    async def list_rooms(self) -> dict[str, RoomInstanceConfig]:
        """Wczytuje i zwraca słownik wszystkich pokoi {id: config}."""
        await self._ensure_defaults()
        return {
            rid: RoomInstanceConfig(id=rid, **content.model_dump())
            for rid, content in (await self._rooms.load_all()).items()
        }

    async def update_room(self, room_id: str, name: str) -> RoomInstanceConfig:
        """Zmienia nazwę istniejącego pokoju. Rzuca ValueError jeśli nie istnieje."""
        await self._ensure_defaults()
        if await self._rooms.load(room_id) is None:
            raise ValueError(f"Pokój o ID '{room_id}' nie istnieje.")
        updated = RoomFileContent(name=name)
        await self._rooms.save(room_id, updated)
        logger.info(f"Zaktualizowano pokój [{room_id}].")
        return RoomInstanceConfig(id=room_id, **updated.model_dump())

    async def delete_room(self, room_id: str) -> bool:
        """Usuwa plik pokoju z dysku. Urządzenia/nadawcy wskazujący na usunięty `room_id`
        po prostu przestają mieć dopasowanie (cicho traktowani jak nieprzypisani,
        patrz `turn_context.render_devices_section`) — bez cascade delete."""
        await self._ensure_defaults()
        return await self._rooms.delete(room_id)

    # --------------------------------------------------------------------------
    # Zadeklarowane urządzenia — jedyne źródło prawdy o tym, co widzi agent
    # --------------------------------------------------------------------------

    async def get_declared_devices(self) -> DeclaredDevicesFileContent:
        """Wczytuje zadeklarowaną listę urządzeń. Brak pliku = pusta lista."""
        await self._ensure_defaults()
        return await self._declared_store.load()

    async def add_declared_device(
        self, entity_id: str, display_name: str | None = None, room_id: str | None = None
    ) -> None:
        """Dodaje encję do zadeklarowanej listy (widoczna dla agenta od tej pory)."""
        await self._ensure_defaults()
        await self._declared_store.upsert(entity_id, DeclaredDeviceEntry(display_name=display_name, room_id=room_id))
        logger.info(f"Zadeklarowano urządzenie [{entity_id}].")

    async def update_declared_device(
        self, entity_id: str, display_name: str | None, room_id: str | None = None
    ) -> DeclaredDeviceEntry:
        """Zmienia `display_name`/`room_id` istniejącego wpisu. Rzuca ValueError jeśli nie istnieje."""
        await self._ensure_defaults()
        if entity_id not in (await self._declared_store.load()).entries:
            raise ValueError(f"Urządzenie '{entity_id}' nie jest zadeklarowane.")
        entry = DeclaredDeviceEntry(display_name=display_name, room_id=room_id)
        await self._declared_store.upsert(entity_id, entry)
        return entry

    async def remove_declared_device(self, entity_id: str) -> bool:
        """Usuwa encję z zadeklarowanej listy (przestaje być widoczna dla agenta)."""
        await self._ensure_defaults()
        removed = await self._declared_store.remove(entity_id)
        if removed:
            logger.info(f"Usunięto deklarację urządzenia [{entity_id}].")
        return removed

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
        return await self._senders_store.load()

    async def register_sender(self, sender_id: str, profile: SenderProfile) -> SenderProfile:
        """Rejestruje lub nadpisuje przypisanie nadawcy do pokoju."""
        await self._ensure_defaults()
        await self._senders_store.upsert(sender_id, profile)
        logger.info(f"Przypisano nadawcę [{sender_id}] do pokoju.")
        return profile

    async def remove_sender(self, sender_id: str) -> bool:
        """Usuwa przypisanie nadawcy."""
        await self._ensure_defaults()
        removed = await self._senders_store.remove(sender_id)
        if removed:
            logger.info(f"Usunięto przypisanie nadawcy [{sender_id}].")
        return removed

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

    async def _describe_target(self, sender_id: str) -> tuple[SenderProfile | None, str | None]:
        """Profil klienta + nazwa jego pokoju — potrzebne narzędziu `speak_in_room`
        do przeliczenia sekcji kontekstu dla nowego celu dostawy."""
        profile = (await self.get_senders()).entries.get(sender_id)
        if profile is None or not profile.room_id:
            return profile, None
        room = (await self.list_rooms()).get(profile.room_id)
        return profile, room.name if room else None

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        """Wkład Świata w jedną turę agenta: tożsamość, fakty i narzędzia.

        Prompt tury dzieli się wzdłuż osi ZMIENNOŚCI, nie tematu (patrz
        `agent/context_provider.py::ContextBuild`): tożsamość (aktywny profil) trafia
        do `system_prompt` i jest stabilna między turami, a wszystko poniżej do
        `turn_context` — prawdziwego tylko teraz. Wcześniej był to jeden sklejony
        string, przez co znacznik czasu zmieniał wiadomość zerową co turę, a tekstu
        faktów nie dało się edytować bez dotykania tożsamości.
        """
        # 1. Profil klienta: gdzie stoi i co potrafi. Liczony PRZED Home Assistantem,
        #    żeby jego niedostępność nigdy nie ucięła ramowania dostawy.
        rooms_by_id = await self.list_rooms()
        profile: SenderProfile | None = None
        if sender_id is not None:
            profile = (await self.get_senders()).entries.get(sender_id)
        current_room = rooms_by_id.get(profile.room_id) if (profile and profile.room_id) else None

        # 2. Home Assistant — łagodna degradacja: brak configu ucina wyłącznie urządzenia.
        config = await self.get_config()
        ha_configured = bool(config.base_url and config.access_token)
        devices: list[Device] = []
        groups: list[DeviceGroup] = []
        client: HomeAssistantClient | None = None
        if ha_configured:
            client = self._build_client(config)
            devices = await self.resolve_devices(client=client)
            groups = [
                DeviceGroup(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids)
                for cfg in (await self.list_groups()).values()
            ]

        # 3. Stan -> tekst. Silnik dostarcza WYŁĄCZNIE dane; o tym, które bloki się
        #    pojawią i w jakiej kolejności, decyduje konfiguracja użytkownika.
        facts = build_turn_facts(
            now=datetime.now(),
            profile=profile,
            current_room=current_room,
            rooms_by_id=rooms_by_id,
            devices=devices,
            groups=groups,
            ha_configured=ha_configured,
        )
        sections = await self._section_store.load()

        # 4. Narzędzia tej tury: własne Świata + (gdy są urządzenia) Home Assistant.
        tools = ToolSet(
            [
                get_time_tool(facts.now),
                speak_in_room_tool(
                    find_speaker=self._find_speaker_by_room,
                    describe_target=self._describe_target,
                    sections=sections,
                    facts=facts,
                ),
            ]
        )
        if devices or groups:
            executor = HomeAssistantToolExecutor(DeviceRegistry(devices, groups), client) if client else None
            tools.add_home_assistant(executor, build_tool_definitions())

        return ContextBuild(
            tool_definitions=tools.definitions,
            system_prompt=(await self._prompt_store.get_active_content()) or None,
            turn_context=render_turn_context(sections, facts),
            dispatch=tools.dispatch,
        )
