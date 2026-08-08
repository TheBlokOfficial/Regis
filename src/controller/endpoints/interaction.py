from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import controller.orchestrator as orchestrator
import controller.agent.session.store as session_store
from controller.agent.session.manager import clear_conversation_history

router_interaction = APIRouter()


class InteractionRequest(BaseModel):
    message: str
    satellite_id: str | None = None
    room: str | None = None


@router_interaction.post("/v1/chat/stream")
async def chat_stream(request: InteractionRequest):
    return StreamingResponse(
        orchestrator.stream_chat(request.message, request.satellite_id, request.room),
        media_type="text/event-stream"
    )


@router_interaction.post("/v1/chat/audio_stream")
async def chat_audio_stream(request: Request, file: UploadFile = File(...)):
    client_id = request.headers.get("X-Client-ID")
    audio_bytes = await file.read()
    
    return StreamingResponse(
        orchestrator.stream_chat_audio(audio_bytes, client_id),
        media_type="text/event-stream"
    )


@router_interaction.post("/v1/clear_history")
async def clear_history(satellite_id: str | None = None):
    """Resetuje historię konwersacji (danej sesji lub wszystkich) w pamięci Kontrolera."""
    clear_conversation_history(satellite_id)
    return {"status": "ok"}


@router_interaction.get("/v1/chat/history")
async def get_history(satellite_id: str | None = None):
    """Zwraca historię konwersacji dla wybranej Satelity / sesji."""
    history = session_store.get_session_history(satellite_id)
    return {"satellite_id": satellite_id or "default", "history": history}


@router_interaction.get("/v1/sessions")
async def get_sessions():
    """Zwraca listę aktywnych sesji konwersacji."""
    active_sessions = []
    for sid, turns in session_store.conversation_sessions.items():
        last_t = session_store.session_last_interaction_times.get(sid, 0.0)
        active_sessions.append({
            "id": sid,
            "turns_count": len(turns),
            "last_interaction": last_t
        })
    return {"sessions": active_sessions}


@router_interaction.get("/v1/rooms")
async def get_rooms():
    from controller.config import loader as config
    from controller.config.schemas import RoomsConfig
    rooms_data = config.load(RoomsConfig).root
    return {"rooms": list(rooms_data.keys())}
