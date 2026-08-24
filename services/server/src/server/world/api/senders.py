"""Rejestr klientów — `sender_id` -> pokój, nazwa i możliwości.

Klient stojący w pokoju jest takim samym bytem World co żarówka: ma trwałe
`capabilities` (`mic`/`speaker`/`text`), z których World wyprowadza ramowanie
odpowiedzi. Rejestracja jest zarazem bramką — nadawca spoza tego rejestru nie
odpali tury (patrz `docs/manifest.md`, sekcja 5, „Bramka rejestracji").
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from shared import DeletionResponse

from server.world.api.mappers import to_sender_dto
from server.world.dto import RegisterSenderRequest, SenderProfileDTO
from server.world.engine import WorldEngine


def create_router(engine: WorldEngine) -> APIRouter:
    router = APIRouter()

    @router.get("/senders", response_model=list[SenderProfileDTO], tags=["World"])
    async def get_senders() -> list[SenderProfileDTO]:
        senders = await engine.get_senders()
        rooms_by_id = await engine.list_rooms()
        return [to_sender_dto(sender_id, profile, rooms_by_id) for sender_id, profile in senders.entries.items()]

    @router.post("/senders", response_model=SenderProfileDTO, status_code=status.HTTP_201_CREATED, tags=["World"])
    async def register_sender(req: RegisterSenderRequest) -> SenderProfileDTO:
        """Upsert wołany z trzech miejsc UI o różnej wiedzy o kliencie — regułę
        „pominięte pole zachowuje obecną wartość" rozstrzyga silnik
        (`WorldEngine.upsert_sender`), nie ta warstwa."""
        profile = await engine.upsert_sender(
            req.sender_id,
            room_id=req.room_id,
            display_name=req.display_name,
            capabilities=req.capabilities,
        )
        return to_sender_dto(req.sender_id, profile, await engine.list_rooms())

    @router.delete("/senders/{sender_id}", response_model=DeletionResponse, tags=["World"])
    async def delete_sender(sender_id: str) -> DeletionResponse:
        if not await engine.remove_sender(sender_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Nadawca '{sender_id}' nie jest zarejestrowany.",
            )
        return DeletionResponse(deleted_id=sender_id)

    return router
