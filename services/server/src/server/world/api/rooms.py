"""Pokoje — pełnoprawny byt World, niezależny od Home Assistant Areas."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from shared import DeletionResponse

from server.world.api.mappers import to_room_dto
from server.world.dto import CreateRoomRequest, RoomDTO, UpdateRoomRequest
from server.world.engine import WorldEngine


def create_router(engine: WorldEngine) -> APIRouter:
    router = APIRouter()

    @router.get("/rooms", response_model=list[RoomDTO], tags=["World"])
    async def get_rooms() -> list[RoomDTO]:
        return [to_room_dto(cfg) for cfg in (await engine.list_rooms()).values()]

    @router.post("/rooms", response_model=RoomDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def create_room(req: CreateRoomRequest) -> RoomDTO:
        return to_room_dto(await engine.create_room(name=req.name, custom_id=req.custom_id))

    @router.put("/rooms/{room_id}", response_model=RoomDTO, tags=["World"])
    async def update_room(room_id: str, req: UpdateRoomRequest) -> RoomDTO:
        try:
            return to_room_dto(await engine.update_room(room_id=room_id, name=req.name))
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err

    @router.delete("/rooms/{room_id}", response_model=DeletionResponse, tags=["World"])
    async def delete_room(room_id: str) -> DeletionResponse:
        """Bez cascade delete: urządzenia i klienci wskazujący na usunięty pokój po
        prostu przestają mieć dopasowanie i są traktowani jak nieprzypisani."""
        if not await engine.delete_room(room_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Pokój o ID '{room_id}' nie istnieje.")
        return DeletionResponse(deleted_id=room_id)

    return router
