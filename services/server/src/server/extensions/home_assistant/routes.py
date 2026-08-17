"""Router REST rozszerzenia Home Assistant — ścieżki WZGLĘDNE.

Montowany przez `network/gateway.py` pod `/api/v1/extensions/home_assistant`
(patrz `NetworkExtension.build_router`, `network/extension_contract.py`) — ten
plik nie zna i nie zakłada własnego prefiksu.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, status

from server.extensions.home_assistant.dto import (
    AddDeclaredDeviceRequest,
    CatalogEntryDTO,
    CreateHAGroupRequest,
    DeclaredDeviceDTO,
    HAGroupDTO,
    HomeAssistantConfigDTO,
    UpdateDeclaredDeviceRequest,
    UpdateHAGroupRequest,
    UpdateHomeAssistantConfigRequest,
)
from server.extensions.home_assistant.models import DeclaredDeviceEntry, Device, HomeAssistantConfig

if TYPE_CHECKING:
    from server.extensions.home_assistant.extension import HomeAssistantExtension


def _mask_token(token: str) -> str:
    """Maskuje token dostępu do ostatnich 4 widocznych znaków — jedno znane pole, bez lookupu schematu."""
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


def create_home_assistant_router(extension: "HomeAssistantExtension") -> APIRouter:
    """Tworzy router dla punktów końcowych konfiguracji, katalogu, zadeklarowanych urządzeń i grup."""
    router = APIRouter()

    # --------------------------------------------------------------------------
    # Konfiguracja singletona
    # --------------------------------------------------------------------------

    @router.get("/config", response_model=HomeAssistantConfigDTO, tags=["Home Assistant"])
    async def get_config() -> HomeAssistantConfigDTO:
        return _to_config_dto(await extension.get_config())

    @router.put("/config", response_model=HomeAssistantConfigDTO, tags=["Home Assistant"])
    async def update_config(req: UpdateHomeAssistantConfigRequest) -> HomeAssistantConfigDTO:
        updated = await extension.save_config(base_url=req.base_url, access_token=req.access_token)
        return _to_config_dto(updated)

    # --------------------------------------------------------------------------
    # Surowy katalog HA — do wyszukiwarki w UI, nie to, co widzi agent
    # --------------------------------------------------------------------------

    @router.get("/catalog", response_model=list[CatalogEntryDTO], tags=["Home Assistant"])
    async def get_catalog() -> list[CatalogEntryDTO]:
        devices = await extension.get_catalog()
        return [CatalogEntryDTO(entity_id=d.id, friendly_name=d.name, kind=d.kind) for d in devices]

    # --------------------------------------------------------------------------
    # Zadeklarowane urządzenia — jedyne źródło prawdy o tym, co widzi agent
    # --------------------------------------------------------------------------

    @router.get("/declared", response_model=list[DeclaredDeviceDTO], tags=["Home Assistant"])
    async def get_declared() -> list[DeclaredDeviceDTO]:
        declared = await extension.get_declared_devices()
        resolved_by_id = {d.id: d for d in await extension.resolve_devices()}
        return [_to_declared_dto(entity_id, entry, resolved_by_id.get(entity_id)) for entity_id, entry in declared.entries.items()]

    @router.post("/declared", response_model=DeclaredDeviceDTO, status_code=status.HTTP_201_CREATED, tags=["Home Assistant"])
    async def add_declared(req: AddDeclaredDeviceRequest) -> DeclaredDeviceDTO:
        await extension.add_declared_device(entity_id=req.entity_id, display_name=req.display_name)
        resolved_by_id = {d.id: d for d in await extension.resolve_devices()}
        return _to_declared_dto(req.entity_id, DeclaredDeviceEntry(display_name=req.display_name), resolved_by_id.get(req.entity_id))

    @router.put("/declared/{entity_id}", response_model=DeclaredDeviceDTO, tags=["Home Assistant"])
    async def update_declared(entity_id: str, req: UpdateDeclaredDeviceRequest) -> DeclaredDeviceDTO:
        try:
            entry = await extension.update_declared_device(entity_id=entity_id, display_name=req.display_name)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        resolved_by_id = {d.id: d for d in await extension.resolve_devices()}
        return _to_declared_dto(entity_id, entry, resolved_by_id.get(entity_id))

    @router.delete("/declared/{entity_id}", tags=["Home Assistant"])
    async def delete_declared(entity_id: str):
        deleted = await extension.remove_declared_device(entity_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Urządzenie '{entity_id}' nie jest zadeklarowane.",
            )
        return {"success": True, "deleted_id": entity_id}

    # --------------------------------------------------------------------------
    # Grupy urządzeń
    # --------------------------------------------------------------------------

    @router.get("/groups", response_model=list[HAGroupDTO], tags=["Home Assistant"])
    async def get_groups() -> list[HAGroupDTO]:
        instances = await extension.list_groups()
        return [HAGroupDTO(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids) for cfg in instances.values()]

    @router.post("/groups", response_model=HAGroupDTO, status_code=status.HTTP_201_CREATED, tags=["Home Assistant"])
    async def create_group(req: CreateHAGroupRequest) -> HAGroupDTO:
        created = await extension.create_group(name=req.name, device_ids=req.device_ids, custom_id=req.custom_id)
        return HAGroupDTO(id=created.id, name=created.name, device_ids=created.device_ids)

    @router.put("/groups/{group_id}", response_model=HAGroupDTO, tags=["Home Assistant"])
    async def update_group(group_id: str, req: UpdateHAGroupRequest) -> HAGroupDTO:
        try:
            updated = await extension.update_group(group_id=group_id, name=req.name, device_ids=req.device_ids)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        return HAGroupDTO(id=updated.id, name=updated.name, device_ids=updated.device_ids)

    @router.delete("/groups/{group_id}", tags=["Home Assistant"])
    async def delete_group(group_id: str):
        deleted = await extension.delete_group(group_id)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grupa o ID '{group_id}' nie istnieje.")
        return {"success": True, "deleted_id": group_id}

    return router
