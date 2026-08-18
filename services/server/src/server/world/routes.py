"""Router REST konfiguracji WorldEngine — ścieżki WZGLĘDNE.

Montowany wprost w `network/gateway.py` pod stałym prefiksem `/api/v1/world`
— sieć zna `WorldEngine` bezpośrednio (jeden, konkretny silnik, nie generyczna
kolekcja rozszerzeń), więc nie potrzeba już protokołu `NetworkExtension`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from server.world.dto import (
    AddDeclaredDeviceRequest,
    CatalogEntryDTO,
    CreateHAGroupRequest,
    DeclaredDeviceDTO,
    HAGroupDTO,
    HomeAssistantConfigDTO,
    RegisterSenderRequest,
    SenderProfileDTO,
    UpdateDeclaredDeviceRequest,
    UpdateHAGroupRequest,
    UpdateHomeAssistantConfigRequest,
)
from server.world.engine import WorldEngine
from server.world.models import DeclaredDeviceEntry, Device, HomeAssistantConfig, SenderProfile


def _mask_token(token: str) -> str:
    """Maskuje token dostępu do ostatnich 4 widocznych znaków."""
    if not token:
        return token
    visible = token[-4:] if len(token) > 4 else ""
    return f"{'•' * (len(token) - len(visible))}{visible}"


def _to_config_dto(cfg: HomeAssistantConfig) -> HomeAssistantConfigDTO:
    return HomeAssistantConfigDTO(base_url=cfg.base_url, access_token=_mask_token(cfg.access_token))


def _to_declared_dto(entity_id: str, entry: DeclaredDeviceEntry, resolved: Device | None) -> DeclaredDeviceDTO:
    return DeclaredDeviceDTO(
        entity_id=entity_id,
        display_name=entry.display_name,
        effective_name=resolved.name if resolved is not None else (entry.display_name or entity_id),
        kind=resolved.kind if resolved is not None else "",
        capabilities=sorted(resolved.capabilities.keys()) if resolved is not None else [],
    )


def _to_sender_dto(sender_id: str, profile: SenderProfile) -> SenderProfileDTO:
    return SenderProfileDTO(sender_id=sender_id, room_key=profile.room_key, room_label=profile.room_label)


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

    # --------------------------------------------------------------------------
    # Surowy katalog HA — do wyszukiwarki w UI, nie to, co widzi agent
    # --------------------------------------------------------------------------

    @router.get("/catalog", response_model=list[CatalogEntryDTO], tags=["World"])
    async def get_catalog() -> list[CatalogEntryDTO]:
        devices = await engine.get_catalog()
        return [CatalogEntryDTO(entity_id=d.id, friendly_name=d.name, kind=d.kind) for d in devices]

    @router.get("/areas", response_model=list[str], tags=["World"])
    async def get_areas() -> list[str]:
        return await engine.list_areas()

    # --------------------------------------------------------------------------
    # Zadeklarowane urządzenia — jedyne źródło prawdy o tym, co widzi agent
    # --------------------------------------------------------------------------

    @router.get("/declared", response_model=list[DeclaredDeviceDTO], tags=["World"])
    async def get_declared() -> list[DeclaredDeviceDTO]:
        declared = await engine.get_declared_devices()
        resolved_by_id = {d.id: d for d in await engine.resolve_devices()}
        return [_to_declared_dto(entity_id, entry, resolved_by_id.get(entity_id)) for entity_id, entry in declared.entries.items()]

    @router.post("/declared", response_model=DeclaredDeviceDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def add_declared(req: AddDeclaredDeviceRequest) -> DeclaredDeviceDTO:
        await engine.add_declared_device(entity_id=req.entity_id, display_name=req.display_name)
        resolved_by_id = {d.id: d for d in await engine.resolve_devices()}
        return _to_declared_dto(req.entity_id, DeclaredDeviceEntry(display_name=req.display_name), resolved_by_id.get(req.entity_id))

    @router.put("/declared/{entity_id}", response_model=DeclaredDeviceDTO, tags=["World"])
    async def update_declared(entity_id: str, req: UpdateDeclaredDeviceRequest) -> DeclaredDeviceDTO:
        try:
            entry = await engine.update_declared_device(entity_id=entity_id, display_name=req.display_name)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        resolved_by_id = {d.id: d for d in await engine.resolve_devices()}
        return _to_declared_dto(entity_id, entry, resolved_by_id.get(entity_id))

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
        return [_to_sender_dto(sender_id, profile) for sender_id, profile in senders.entries.items()]

    @router.post("/senders", response_model=SenderProfileDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def register_sender(req: RegisterSenderRequest) -> SenderProfileDTO:
        profile = SenderProfile(room_key=req.room_key, room_label=req.room_label)
        await engine.register_sender(req.sender_id, profile)
        return _to_sender_dto(req.sender_id, profile)

    @router.delete("/senders/{sender_id}", tags=["World"])
    async def delete_sender(sender_id: str):
        deleted = await engine.remove_sender(sender_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Nadawca '{sender_id}' nie jest zarejestrowany.")
        return {"success": True, "deleted_id": sender_id}

    return router
