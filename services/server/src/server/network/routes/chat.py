import asyncio
import json
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from shared import (
    CancelChatApiRequest,
    ChatResponseDTO,
    SendChatMessageRequest,
)
from server.agent import AgentEngine


def create_chat_router(agent_engine: AgentEngine) -> APIRouter:
    """Tworzy router dla punktów końcowych interakcji z Agentem."""
    router = APIRouter()

    @router.post(
        "/api/v1/chat",
        response_model=ChatResponseDTO,
        summary="Wysyła wiadomość do Agenta i zwraca pełną odpowiedź w jednym żądaniu",
        tags=["Chat & Sessions"],
    )
    async def chat_interact(req: SendChatMessageRequest) -> ChatResponseDTO:
        if agent_engine.is_session_busy(req.session_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sesja '{req.session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.",
            )
        try:
            return await agent_engine.interact(
                session_id=req.session_id,
                prompt=req.message,
                sender_id=req.sender_id,
            )
        except ValueError as err:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Błąd generowania odpowiedzi przez Agenta: {err}",
            )

    @router.post(
        "/api/v1/chat/stream",
        summary="Wysyła wiadomość do Agenta i strumieniuje odpowiedź w czasie rzeczywistym via SSE",
        tags=["Chat & Sessions"],
    )
    async def chat_interact_stream(req: SendChatMessageRequest):
        if agent_engine.is_session_busy(req.session_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Sesja '{req.session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.",
            )

        async def event_generator():
            try:
                async for event in agent_engine.interact_stream(
                    session_id=req.session_id,
                    prompt=req.message,
                    sender_id=req.sender_id,
                ):
                    yield f"data: {json.dumps({**event.payload, 'type': event.type})}\n\n"
                yield "data: [DONE]\n\n"
            except asyncio.CancelledError:
                yield f"data: {json.dumps({'type': 'cancelled'})}\n\n"
                yield "data: [DONE]\n\n"
            except Exception as err:
                error_payload = json.dumps({"type": "error", "error": str(err)})
                yield f"data: {error_payload}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @router.post(
        "/api/v1/chat/cancel",
        summary="Anuluje aktywne generowanie odpowiedzi dla podanej sesji (Web, Satelita, Cron)",
        tags=["Chat & Sessions"],
    )
    async def cancel_chat_interact(req: CancelChatApiRequest):
        cancelled = await agent_engine.cancel_interaction(req.session_id)
        return {"success": cancelled, "session_id": req.session_id}

    return router
