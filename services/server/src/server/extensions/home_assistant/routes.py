"""Router REST rozszerzenia Home Assistant — ścieżki WZGLĘDNE.

Montowany przez `network/gateway.py` pod `/api/v1/extensions/home_assistant`
(patrz `NetworkExtension.build_router`, `network/extension_contract.py`) — ten
plik nie zna i nie zakłada własnego prefiksu.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, status

from server.extensions.home_assistant.dto import (
    CatalogEntryDTO,
    CreateHAConnectionRequest,
    CreateHAGroupRequest,
    HAConnectionDTO,
    HAGroupDTO,
    UpdateCatalogRequest,
    UpdateHAConnectionRequest,
    UpdateHAGroupRequest,
)
from server.extensions.home_assistant.models import DeviceDeclarationEntry, DeviceDeclarationFileContent, HAConnectionConfig

if TYPE_CHECKING:
    from server.extensions.home_assistant.extension import HomeAssistantExtension


def _mask_token(token: str) -> str:
    """Maskuje token dostępu do ostatnich 4 widocznych znaków — jedno znane pole, bez lookupu schematu."""
    if not token:
        return token
    visible = token[-4:] if len(token) > 4 else ""
    return f"{'•' * (len(token) - len(visible))}{visible}"


def _to_dto(cfg: HAConnectionConfig) -> HAConnectionDTO:
    return HAConnectionDTO(
        id=cfg.id,
        name=cfg.name,
        base_url=cfg.base_url,
        access_token=_mask_token(cfg.access_token),
        enabled=cfg.enabled,
    )


def create_home_assistant_router(extension: "HomeAssistantExtension") -> APIRouter:
    """Tworzy router dla punktów końcowych połączeń, katalogu i grup Home Assistant."""
    router = APIRouter()

    # --------------------------------------------------------------------------
    # Połączenia
    # --------------------------------------------------------------------------

    @router.get("/connections", response_model=list[HAConnectionDTO], tags=["Home Assistant"])
    async def get_connections() -> list[HAConnectionDTO]:
        instances = await extension.list_connections()
        return [_to_dto(cfg) for cfg in instances.values()]

    @router.post("/connections", response_model=HAConnectionDTO, status_code=status.HTTP_201_CREATED, tags=["Home Assistant"])
    async def create_connection(req: CreateHAConnectionRequest) -> HAConnectionDTO:
        created = await extension.create_connection(
            name=req.name,
            base_url=req.base_url,
            access_token=req.access_token,
            enabled=req.enabled,
            custom_id=req.custom_id,
        )
        return _to_dto(created)

    @router.put("/connections/{connection_id}", response_model=HAConnectionDTO, tags=["Home Assistant"])
    async def update_connection(connection_id: str, req: UpdateHAConnectionRequest) -> HAConnectionDTO:
        try:
            updated = await extension.update_connection(
                connection_id=connection_id,
                name=req.name,
                base_url=req.base_url,
                access_token=req.access_token,
                enabled=req.enabled,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err))
        return _to_dto(updated)

    @router.delete("/connections/{connection_id}", tags=["Home Assistant"])
    async def delete_connection(connection_id: str):
        deleted = await extension.delete_connection(connection_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Połączenie o ID '{connection_id}' nie istnieje.",
            )
        return {"success": True, "deleted_id": connection_id}

    # --------------------------------------------------------------------------
    # Katalog urządzeń — per połączenie, z zastosowaną deklaracją widoczności
    # --------------------------------------------------------------------------

    @router.get("/connections/{connection_id}/catalog", response_model=list[CatalogEntryDTO], tags=["Home Assistant"])
    async def get_catalog(connection_id: str) -> list[CatalogEntryDTO]:
        connections = await extension.list_connections()
        config = connections.get(connection_id)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Połączenie o ID '{connection_id}' nie istnieje.")

        entries = await extension.resolve_devices(connection_id, config)
        return [
            CatalogEntryDTO(ref=device.id, label=device.name, kind=device.kind, capabilities=sorted(device.capabilities), enabled=enabled)
            for device, enabled in entries
        ]

    @router.put("/connections/{connection_id}/catalog", response_model=list[CatalogEntryDTO], tags=["Home Assistant"])
    async def update_catalog(connection_id: str, req: UpdateCatalogRequest) -> list[CatalogEntryDTO]:
        connections = await extension.list_connections()
        config = connections.get(connection_id)
        if config is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Połączenie o ID '{connection_id}' nie istnieje.")

        prefix = f"{connection_id}:"
        entries = {
            entry.ref[len(prefix):] if entry.ref.startswith(prefix) else entry.ref: DeviceDeclarationEntry(
                enabled=entry.enabled, display_name=entry.display_name
            )
            for entry in req.entries
        }
        await extension.save_declaration(connection_id, DeviceDeclarationFileContent(entries=entries))

        resolved = await extension.resolve_devices(connection_id, config)
        return [
            CatalogEntryDTO(ref=device.id, label=device.name, kind=device.kind, capabilities=sorted(device.capabilities), enabled=enabled)
            for device, enabled in resolved
        ]

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
