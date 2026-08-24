"""Zadeklarowane urządzenia — jedyne źródło prawdy o tym, co widzi agent.

Model jest **opt-in**: brak wpisu oznacza niewidoczność, niezależnie od tego, czy
encja istnieje po stronie Home Assistanta. Surowy katalog wszystkich encji żyje
osobno (`home_assistant.py`) i służy wyłącznie wyszukiwarce w UI.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from shared import DeletionResponse

from server.world.api.mappers import to_declared_dto
from server.world.dto import AddDeclaredDeviceRequest, DeclaredDeviceDTO, UpdateDeclaredDeviceRequest
from server.world.engine import WorldEngine
from server.world.models import DeclaredDeviceEntry


def create_router(engine: WorldEngine) -> APIRouter:
    router = APIRouter()

    async def _resolved_and_rooms():
        """Zadeklarowana encja bez odpowiednika po stronie HA nie ma czego pokazać poza
        własnym `entity_id` — stąd join w każdej odpowiedzi, nie tylko na liście."""
        return (
            {d.id: d for d in await engine.resolve_devices()},
            await engine.list_rooms(),
        )

    @router.get("/declared", response_model=list[DeclaredDeviceDTO], tags=["World"])
    async def get_declared() -> list[DeclaredDeviceDTO]:
        declared = await engine.get_declared_devices()
        resolved_by_id, rooms_by_id = await _resolved_and_rooms()
        return [
            to_declared_dto(entity_id, entry, resolved_by_id.get(entity_id), rooms_by_id)
            for entity_id, entry in declared.entries.items()
        ]

    @router.post("/declared", response_model=DeclaredDeviceDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def add_declared(req: AddDeclaredDeviceRequest) -> DeclaredDeviceDTO:
        await engine.add_declared_device(entity_id=req.entity_id, display_name=req.display_name, room_id=req.room_id)
        resolved_by_id, rooms_by_id = await _resolved_and_rooms()
        return to_declared_dto(
            req.entity_id,
            DeclaredDeviceEntry(display_name=req.display_name, room_id=req.room_id),
            resolved_by_id.get(req.entity_id),
            rooms_by_id,
        )

    @router.put("/declared/{entity_id}", response_model=DeclaredDeviceDTO, tags=["World"])
    async def update_declared(entity_id: str, req: UpdateDeclaredDeviceRequest) -> DeclaredDeviceDTO:
        try:
            entry = await engine.update_declared_device(
                entity_id=entity_id, display_name=req.display_name, room_id=req.room_id
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
        resolved_by_id, rooms_by_id = await _resolved_and_rooms()
        return to_declared_dto(entity_id, entry, resolved_by_id.get(entity_id), rooms_by_id)

    @router.delete("/declared/{entity_id}", response_model=DeletionResponse, tags=["World"])
    async def delete_declared(entity_id: str) -> DeletionResponse:
        if not await engine.remove_declared_device(entity_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Urządzenie '{entity_id}' nie jest zadeklarowane.",
            )
        return DeletionResponse(deleted_id=entity_id)

    return router
