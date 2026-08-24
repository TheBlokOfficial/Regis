"""Grupy urządzeń — nazwane zestawy encji, wygodny skrót dla agenta.

Nie są jedynym sposobem adresowania wielu urządzeń naraz: `entity_id` w narzędziach
przyjmuje też tablicę (patrz `world/tools/home_assistant.py`). Grupa przydaje się
tam, gdzie zestaw jest stały i ma sensowną nazwę („Wszystkie światła").
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from shared import DeletionResponse

from server.world.dto import CreateHAGroupRequest, HAGroupDTO, UpdateHAGroupRequest
from server.world.engine import WorldEngine


def create_router(engine: WorldEngine) -> APIRouter:
    router = APIRouter()

    @router.get("/groups", response_model=list[HAGroupDTO], tags=["World"])
    async def get_groups() -> list[HAGroupDTO]:
        return [
            HAGroupDTO(id=cfg.id, name=cfg.name, device_ids=cfg.device_ids)
            for cfg in (await engine.list_groups()).values()
        ]

    @router.post("/groups", response_model=HAGroupDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def create_group(req: CreateHAGroupRequest) -> HAGroupDTO:
        created = await engine.create_group(name=req.name, device_ids=req.device_ids, custom_id=req.custom_id)
        return HAGroupDTO(id=created.id, name=created.name, device_ids=created.device_ids)

    @router.put("/groups/{group_id}", response_model=HAGroupDTO, tags=["World"])
    async def update_group(group_id: str, req: UpdateHAGroupRequest) -> HAGroupDTO:
        try:
            updated = await engine.update_group(group_id=group_id, name=req.name, device_ids=req.device_ids)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
        return HAGroupDTO(id=updated.id, name=updated.name, device_ids=updated.device_ids)

    @router.delete("/groups/{group_id}", response_model=DeletionResponse, tags=["World"])
    async def delete_group(group_id: str) -> DeletionResponse:
        if not await engine.delete_group(group_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Grupa o ID '{group_id}' nie istnieje.")
        return DeletionResponse(deleted_id=group_id)

    return router
