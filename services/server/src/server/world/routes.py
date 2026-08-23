"""Router REST konfiguracji WorldEngine — ścieżki WZGLĘDNE.

Montowany wprost w `network/gateway.py` pod stałym prefiksem `/api/v1/world`
— sieć zna `WorldEngine` bezpośrednio (jeden, konkretny silnik, nie generyczna
kolekcja rozszerzeń), więc nie potrzeba już protokołu `NetworkExtension`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from shared import CreatePromptRequest, PromptDTO, PromptListResponse, UpdatePromptRequest

from server.world.dto import (
    AddDeclaredDeviceRequest,
    CatalogEntryDTO,
    CreateHAGroupRequest,
    CreateRoomRequest,
    DeclaredDeviceDTO,
    HAGroupDTO,
    ConditionSpecDTO,
    HomeAssistantConfigDTO,
    PlaceholderSpecDTO,
    PromptPreviewResponse,
    PromptSectionDTO,
    PromptSectionsResponse,
    RegisterSenderRequest,
    RoomDTO,
    SenderProfileDTO,
    TestConnectionResponse,
    TestHAConnectionRequest,
    UpdateDeclaredDeviceRequest,
    UpdateHAGroupRequest,
    UpdateHomeAssistantConfigRequest,
    UpdatePromptSectionsRequest,
    UpdateRoomRequest,
)
from server.world.engine import WorldEngine
from server.world.prompt_sections import (
    CONDITION_SPECS,
    PLACEHOLDER_SPECS,
    PromptSection,
    PromptSectionsConfig,
    section_warnings,
)
from server.world.models import DeclaredDeviceEntry, Device, HomeAssistantConfig, RoomInstanceConfig, SenderProfile


def _mask_token(token: str) -> str:
    """Maskuje token dostępu do ostatnich 4 widocznych znaków."""
    if not token:
        return token
    visible = token[-4:] if len(token) > 4 else ""
    return f"{'•' * (len(token) - len(visible))}{visible}"


def _to_config_dto(cfg: HomeAssistantConfig) -> HomeAssistantConfigDTO:
    return HomeAssistantConfigDTO(base_url=cfg.base_url, access_token=_mask_token(cfg.access_token))


def _to_room_dto(cfg: RoomInstanceConfig) -> RoomDTO:
    return RoomDTO(id=cfg.id, name=cfg.name)


def _to_declared_dto(
    entity_id: str, entry: DeclaredDeviceEntry, resolved: Device | None, rooms_by_id: dict[str, RoomInstanceConfig]
) -> DeclaredDeviceDTO:
    room = rooms_by_id.get(entry.room_id) if entry.room_id else None
    return DeclaredDeviceDTO(
        entity_id=entity_id,
        display_name=entry.display_name,
        effective_name=resolved.name if resolved is not None else (entry.display_name or entity_id),
        kind=resolved.kind if resolved is not None else "",
        capabilities=sorted(resolved.capabilities.keys()) if resolved is not None else [],
        room_id=entry.room_id,
        room_name=room.name if room is not None else None,
    )


def _to_sections_response(config: PromptSectionsConfig) -> PromptSectionsResponse:
    """Sekcje w kolejności zapisu (= kolejność w prompcie) wraz z metadanymi
    warunków i podstawień, żeby UI nie duplikowało etykiet."""
    return PromptSectionsResponse(
        sections=[
            PromptSectionDTO(
                id=section.id,
                label=section.label,
                text=section.text,
                condition=section.condition,
                condition_param=section.condition_param,
                negated=section.negated,
                warnings=section_warnings(section),
            )
            for section in config.sections
        ],
        conditions=[
            ConditionSpecDTO(key=spec.key, label=spec.label, param_source=spec.param_source)
            for spec in CONDITION_SPECS
        ],
        placeholders=[
            PlaceholderSpecDTO(token=spec.token, label=spec.label, guaranteed_by=list(spec.guaranteed_by))
            for spec in PLACEHOLDER_SPECS
        ],
    )


def _to_sender_dto(sender_id: str, profile: SenderProfile, rooms_by_id: dict[str, RoomInstanceConfig]) -> SenderProfileDTO:
    room = rooms_by_id.get(profile.room_id) if profile.room_id else None
    return SenderProfileDTO(
        sender_id=sender_id,
        display_name=profile.display_name,
        room_id=profile.room_id,
        room_name=room.name if room is not None else None,
        # Posortowane — `frozenset` nie ma kolejności, a UI renderuje to wprost;
        # bez sortowania kolejność potrafiłaby się zmieniać między odpowiedziami.
        capabilities=sorted(profile.capabilities),
    )


def create_world_router(engine: WorldEngine) -> APIRouter:
    """Tworzy router dla punktów końcowych konfiguracji Home Assistant i satelit."""
    router = APIRouter()

    # --------------------------------------------------------------------------
    # Konfiguracja singletona Home Assistant
    # --------------------------------------------------------------------------

    @router.get("/config", response_model=HomeAssistantConfigDTO, tags=["World"])
    async def get_config() -> HomeAssistantConfigDTO:
        return _to_config_dto(await engine.get_config())

    @router.put("/config", response_model=HomeAssistantConfigDTO, tags=["World"])
    async def update_config(req: UpdateHomeAssistantConfigRequest) -> HomeAssistantConfigDTO:
        updated = await engine.save_config(base_url=req.base_url, access_token=req.access_token)
        return _to_config_dto(updated)

    @router.post("/config/test", response_model=TestConnectionResponse, tags=["World"])
    async def test_config(req: TestHAConnectionRequest) -> TestConnectionResponse:
        ok, message = await engine.test_connection(base_url=req.base_url, access_token=req.access_token)
        return TestConnectionResponse(ok=ok, message=message)

    # --------------------------------------------------------------------------
    # Surowy katalog HA — do wyszukiwarki w UI, nie to, co widzi agent
    # --------------------------------------------------------------------------

    @router.get("/catalog", response_model=list[CatalogEntryDTO], tags=["World"])
    async def get_catalog() -> list[CatalogEntryDTO]:
        devices = await engine.get_catalog()
        return [CatalogEntryDTO(entity_id=d.id, friendly_name=d.name, kind=d.kind, ha_area=d.area) for d in devices]

    # --------------------------------------------------------------------------
    # Pokoje — pełnoprawny byt World, niezależny od Home Assistant Areas
    # --------------------------------------------------------------------------

    @router.get("/rooms", response_model=list[RoomDTO], tags=["World"])
    async def get_rooms() -> list[RoomDTO]:
        instances = await engine.list_rooms()
        return [_to_room_dto(cfg) for cfg in instances.values()]

    @router.post("/rooms", response_model=RoomDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def create_room(req: CreateRoomRequest) -> RoomDTO:
        created = await engine.create_room(name=req.name, custom_id=req.custom_id)
        return _to_room_dto(created)

    @router.put("/rooms/{room_id}", response_model=RoomDTO, tags=["World"])
    async def update_room(room_id: str, req: UpdateRoomRequest) -> RoomDTO:
        try:
            updated = await engine.update_room(room_id=room_id, name=req.name)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        return _to_room_dto(updated)

    @router.delete("/rooms/{room_id}", tags=["World"])
    async def delete_room(room_id: str):
        deleted = await engine.delete_room(room_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pokój o ID '{room_id}' nie istnieje.")
        return {"success": True, "deleted_id": room_id}

    # --------------------------------------------------------------------------
    # Zadeklarowane urządzenia — jedyne źródło prawdy o tym, co widzi agent
    # --------------------------------------------------------------------------

    @router.get("/declared", response_model=list[DeclaredDeviceDTO], tags=["World"])
    async def get_declared() -> list[DeclaredDeviceDTO]:
        declared = await engine.get_declared_devices()
        resolved_by_id = {d.id: d for d in await engine.resolve_devices()}
        rooms_by_id = await engine.list_rooms()
        return [
            _to_declared_dto(entity_id, entry, resolved_by_id.get(entity_id), rooms_by_id)
            for entity_id, entry in declared.entries.items()
        ]

    @router.post("/declared", response_model=DeclaredDeviceDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def add_declared(req: AddDeclaredDeviceRequest) -> DeclaredDeviceDTO:
        await engine.add_declared_device(entity_id=req.entity_id, display_name=req.display_name, room_id=req.room_id)
        resolved_by_id = {d.id: d for d in await engine.resolve_devices()}
        rooms_by_id = await engine.list_rooms()
        return _to_declared_dto(
            req.entity_id,
            DeclaredDeviceEntry(display_name=req.display_name, room_id=req.room_id),
            resolved_by_id.get(req.entity_id),
            rooms_by_id,
        )

    @router.put("/declared/{entity_id}", response_model=DeclaredDeviceDTO, tags=["World"])
    async def update_declared(entity_id: str, req: UpdateDeclaredDeviceRequest) -> DeclaredDeviceDTO:
        try:
            entry = await engine.update_declared_device(entity_id=entity_id, display_name=req.display_name, room_id=req.room_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        resolved_by_id = {d.id: d for d in await engine.resolve_devices()}
        rooms_by_id = await engine.list_rooms()
        return _to_declared_dto(entity_id, entry, resolved_by_id.get(entity_id), rooms_by_id)

    @router.delete("/declared/{entity_id}", tags=["World"])
    async def delete_declared(entity_id: str):
        deleted = await engine.remove_declared_device(entity_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Urządzenie '{entity_id}' nie jest zadeklarowane.",
            )
        return {"success": True, "deleted_id": entity_id}

    # --------------------------------------------------------------------------
    # Grupy urządzeń
    # --------------------------------------------------------------------------

    @router.get("/groups", response_model=list[HAGroupDTO], tags=["World"])
    async def get_groups() -> list[HAGroupDTO]:
        instances = await engine.list_groups()
        return [HAGroupDTO(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids) for cfg in instances.values()]

    @router.post("/groups", response_model=HAGroupDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def create_group(req: CreateHAGroupRequest) -> HAGroupDTO:
        created = await engine.create_group(name=req.name, device_ids=req.device_ids, custom_id=req.custom_id)
        return HAGroupDTO(id=created.id, name=created.name, device_ids=created.device_ids)

    @router.put("/groups/{group_id}", response_model=HAGroupDTO, tags=["World"])
    async def update_group(group_id: str, req: UpdateHAGroupRequest) -> HAGroupDTO:
        try:
            updated = await engine.update_group(group_id=group_id, name=req.name, device_ids=req.device_ids)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        return HAGroupDTO(id=updated.id, name=updated.name, device_ids=updated.device_ids)

    @router.delete("/groups/{group_id}", tags=["World"])
    async def delete_group(group_id: str):
        deleted = await engine.delete_group(group_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grupa o ID '{group_id}' nie istnieje.")
        return {"success": True, "deleted_id": group_id}

    # --------------------------------------------------------------------------
    # Nadawcy — sender_id -> pokój (zero wiedzy o kanale/urządzeniu, patrz world/models.py)
    # --------------------------------------------------------------------------

    @router.get("/senders", response_model=list[SenderProfileDTO], tags=["World"])
    async def get_senders() -> list[SenderProfileDTO]:
        senders = await engine.get_senders()
        rooms_by_id = await engine.list_rooms()
        return [_to_sender_dto(sender_id, profile, rooms_by_id) for sender_id, profile in senders.entries.items()]

    @router.post("/senders", response_model=SenderProfileDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def register_sender(req: RegisterSenderRequest) -> SenderProfileDTO:
        # Upsert służy dwóm scenariuszom o różnej wiedzy: rejestracji z zakładki
        # Klienci (zna capabilities z handshake) i zmianie pokoju z zakładki Świat
        # (nie zna ich w ogóle). Puste `capabilities` znaczy więc "zachowaj obecne",
        # nigdy "wyczyść" — ten sam wzorzec co puste pole tokenu w konfiguracji HA,
        # bez którego picker pokoju kasowałby capabilities przy każdej zmianie.
        existing = (await engine.get_senders()).entries.get(req.sender_id)
        capabilities = (
            frozenset(req.capabilities)
            if req.capabilities
            else (existing.capabilities if existing is not None else frozenset())
        )
        # Nazwa idzie tą samą logiką co capabilities: pominięta (`None`) znaczy "zachowaj",
        # bo picker pokoju w zakładce Świat nic o niej nie wie i nie może jej kasować przy
        # każdej zmianie przypisania. Wyczyszczenie nazwy jest osobną, jawną intencją —
        # pusty string. `room_id` **nie** dostaje tej semantyki: tam `None` to legalne
        # "— brak pokoju —" z tego samego pickera.
        display_name = (
            (existing.display_name if existing is not None else None)
            if req.display_name is None
            else (req.display_name.strip() or None)
        )
        profile = SenderProfile(display_name=display_name, room_id=req.room_id, capabilities=capabilities)
        await engine.register_sender(req.sender_id, profile)
        rooms_by_id = await engine.list_rooms()
        return _to_sender_dto(req.sender_id, profile, rooms_by_id)

    @router.delete("/senders/{sender_id}", tags=["World"])
    async def delete_sender(sender_id: str):
        deleted = await engine.remove_sender(sender_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Nadawca '{sender_id}' nie jest zarejestrowany.")
        return {"success": True, "deleted_id": sender_id}

    # --------------------------------------------------------------------------
    # Sekcje kontekstu tury — edytowalny tekst faktów wstrzykiwanych co turę
    # --------------------------------------------------------------------------

    @router.get("/prompt-sections", response_model=PromptSectionsResponse, tags=["World"])
    async def get_prompt_sections() -> PromptSectionsResponse:
        return _to_sections_response(await engine.get_prompt_sections())

    @router.put("/prompt-sections", response_model=PromptSectionsResponse, tags=["World"])
    async def update_prompt_sections(req: UpdatePromptSectionsRequest) -> PromptSectionsResponse:
        sections = [
            PromptSection(
                id=dto.id,
                label=dto.label,
                text=dto.text,
                condition=dto.condition,
                condition_param=dto.condition_param,
                negated=dto.negated,
            )
            for dto in req.sections
        ]
        try:
            config = await engine.save_prompt_sections(sections)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        return _to_sections_response(config)

    @router.post("/prompt-sections/reset", response_model=PromptSectionsResponse, tags=["World"])
    async def reset_prompt_sections() -> PromptSectionsResponse:
        return _to_sections_response(await engine.reset_prompt_sections())

    @router.get("/prompt-sections/preview", response_model=PromptPreviewResponse, tags=["World"])
    async def preview_prompt_sections(sender_id: str | None = None) -> PromptPreviewResponse:
        """Podgląd składa się przez `WorldEngine.build()`, czyli DOKŁADNIE tę samą
        ścieżkę co realna tura — łącznie z odpytaniem Home Assistant. Osobna,
        "szybsza" ścieżka renderowania prędzej czy później rozjechałaby się z
        produkcyjną i podgląd przestałby cokolwiek dowodzić."""
        build = await engine.build(sender_id=sender_id)
        return PromptPreviewResponse(turn_context=build.turn_context or "", sender_id=sender_id)

    # --------------------------------------------------------------------------
    # Profile promptu — tożsamość Świata, do 3 przełączalnych profili
    # --------------------------------------------------------------------------

    @router.get("/prompts", response_model=PromptListResponse, tags=["World"])
    async def list_prompts() -> PromptListResponse:
        instances = await engine.list_prompts()
        active_id = await engine.get_active_prompt_id()
        prompts = [PromptDTO(is_active=(inst.id == active_id), **inst.model_dump()) for inst in instances]
        return PromptListResponse(prompts=prompts, active_id=active_id)

    @router.post("/prompts", response_model=PromptDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def create_prompt(req: CreatePromptRequest) -> PromptDTO:
        try:
            instance = await engine.create_prompt(
                name=req.name, content=req.content, description=req.description,
                custom_id=req.custom_id, set_active=req.set_active,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        active_id = await engine.get_active_prompt_id()
        return PromptDTO(is_active=(instance.id == active_id), **instance.model_dump())

    @router.put("/prompts/{prompt_id}", response_model=PromptDTO, tags=["World"])
    async def update_prompt(prompt_id: str, req: UpdatePromptRequest) -> PromptDTO:
        try:
            instance = await engine.update_prompt(prompt_id, name=req.name, content=req.content, description=req.description)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        active_id = await engine.get_active_prompt_id()
        return PromptDTO(is_active=(instance.id == active_id), **instance.model_dump())

    @router.delete("/prompts/{prompt_id}", tags=["World"])
    async def delete_prompt(prompt_id: str):
        try:
            deleted = await engine.delete_prompt(prompt_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Profil promptu '{prompt_id}' nie istnieje.")
        return {"success": True, "prompt_id": prompt_id}

    @router.put("/prompts/{prompt_id}/activate", response_model=PromptDTO, tags=["World"])
    async def activate_prompt(prompt_id: str) -> PromptDTO:
        try:
            await engine.set_active_prompt(prompt_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        instance = await engine.get_prompt(prompt_id)
        return PromptDTO(is_active=True, **instance.model_dump())  # type: ignore[union-attr]

    return router
