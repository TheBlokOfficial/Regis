import json
import time

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from shared import (
    ChatMessageDTO,
    ChatSessionHistoryResponse,
    ChatSessionListResponse,
    ChatSessionSummaryDTO,
)

from server.agent import AgentEngine


class CreateSessionApiRequest(BaseModel):
    """Żądanie utrwalenia nowej sesji przez API."""

    title: str = Field(default="Nowa konwersacja", description="Tytuł nowej sesji")
    custom_id: str | None = Field(default=None, description="Opcjonalne własne ID sesji (np. session_custom)")


def create_sessions_router(agent_engine: AgentEngine) -> APIRouter:
    """Tworzy router dla punktów końcowych zarządzania sesjami konwersacji."""
    router = APIRouter()

    @router.get(
        "/api/v1/chat/sessions",
        response_model=ChatSessionListResponse,
        summary="Pobiera listę wszystkich aktywnych i zapisanych sesji konwersacji z backendu",
        tags=["Chat & Sessions"],
    )
    async def get_chat_sessions() -> ChatSessionListResponse:
        summaries = agent_engine.memory_manager.list_session_summaries()
        for summary in summaries:
            if agent_engine.is_session_busy(summary.session_id):
                summary.is_generating = True
        return ChatSessionListResponse(sessions=summaries)

    @router.post(
        "/api/v1/chat/sessions",
        response_model=ChatSessionSummaryDTO,
        status_code=status.HTTP_201_CREATED,
        summary="Tworzy nową sesję konwersacji w pamięci i na dysku",
        tags=["Chat & Sessions"],
    )
    async def create_chat_session(req: CreateSessionApiRequest) -> ChatSessionSummaryDTO:
        try:
            session = agent_engine.memory_manager.create_session(
                title=req.title,
                custom_id=req.custom_id,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
        return session.to_summary()

    @router.get(
        "/api/v1/chat/sessions/{session_id}/history",
        response_model=ChatSessionHistoryResponse,
        summary="Pobiera pełną historię wiadomości oraz metadane konkretnej sesji",
        tags=["Chat & Sessions"],
    )
    async def get_chat_session_history(session_id: str) -> ChatSessionHistoryResponse:
        try:
            session = agent_engine.memory_manager.get_or_create_session(session_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
        messages = list(session.get_history())
        is_generating = agent_engine.is_session_busy(session_id)
        if is_generating:
            buf = agent_engine.get_generation_buffer(session_id)
            if buf is not None:
                messages.append(
                    ChatMessageDTO(
                        role="assistant",
                        content=buf,
                        timestamp=time.time(),
                        metadata={"is_partial": True},
                    )
                )

        return ChatSessionHistoryResponse(
            session_id=session.session_id,
            title=session.title,
            messages=messages,
            created_at=session.created_at,
            updated_at=session.updated_at,
            is_generating=is_generating,
        )

    @router.get(
        "/api/v1/chat/sessions/{session_id}/watch",
        summary="Obserwuje sesje w czasie rzeczywistym przez SSE - niezaleznie od tego, kto zainicjowal ture (Web/satelita/cron/inna karta)",
        tags=["Chat & Sessions"],
    )
    async def watch_chat_session(session_id: str):
        """Cienki wrapper wokol `AgentEngine.watch_session()` — polaczenie zyje tak dlugo,
        jak dlugo klient (typowo karta przegladarki) go nie zamknie; kazda przyszla tura tej
        sesji, niezaleznie od inicjatora, doreczana jest tym samym strumieniem."""

        async def event_generator():
            async for event in agent_engine.watch_session(session_id):
                yield f"data: {json.dumps({**event.payload, 'type': event.type})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @router.delete(
        "/api/v1/chat/sessions/{session_id}",
        summary="Usuwa historię i plik sesji z dysku serwera",
        tags=["Chat & Sessions"],
    )
    async def delete_chat_session(session_id: str):
        try:
            deleted = agent_engine.memory_manager.delete_session(session_id)
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Sesja o ID '{session_id}' nie istnieje.",
            )
        return {"success": True, "deleted_id": session_id}

    return router
