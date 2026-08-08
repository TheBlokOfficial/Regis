import json
from fastapi import APIRouter, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import controller.agent.session.store as session_store
from controller.core.message_bus import message_bus
from controller.messages import (
    TextMessage, 
    AudioMessage, 
    PlayAudioMessage, 
    ResumeSatelliteMessage, 
    ClearHistoryMessage
)


router_interaction = APIRouter()


class InteractionRequest(BaseModel):
    message: str
    satellite_id: str | None = None
    room: str | None = None


async def _format_sse_text_stream(event_generator):
    async for item in event_generator:
        yield f"data: {json.dumps(item)}\n\n"


async def _format_sse_audio_stream(event_generator, client_id: str | None = None):
    has_tts = False
    async for item in event_generator:
        if item["type"] == "tts_audio":
            has_tts = True
            if client_id:
                await message_bus.publish(
                    PlayAudioMessage(client_id=client_id, audio_b64=item.get("content", ""))
                )
            continue  # Nie przepuszczaj tts_audio przez SSE

        yield f"data: {json.dumps(item)}\n\n"

        if item["type"] in ("done", "error"):
            if not has_tts and client_id:
                await message_bus.publish(ResumeSatelliteMessage(client_id=client_id))
            break


@router_interaction.post("/v1/chat/stream")
async def chat_stream(request: InteractionRequest):
    msg = TextMessage(
        text=request.message,
        sender=request.satellite_id or "web_ui",
    )
    generator = await message_bus.publish(msg)
    return StreamingResponse(
        _format_sse_text_stream(generator),
        media_type="text/event-stream"
    )


@router_interaction.post("/v1/chat/audio_stream")
async def chat_audio_stream(request: Request, file: UploadFile = File(...)):
    client_id = request.headers.get("X-Client-ID")
    audio_bytes = await file.read()

    msg = AudioMessage(
        audio_bytes=audio_bytes,
        sender=client_id or "web_ui",
    )
    generator = await message_bus.publish(msg)
    return StreamingResponse(
        _format_sse_audio_stream(generator, client_id),
        media_type="text/event-stream"
    )













@router_interaction.post("/v1/clear_history")
async def clear_history(satellite_id: str | None = None):
    """Resetuje historię konwersacji (danej sesji lub wszystkich) w pamięci Kontrolera."""
    await message_bus.publish(ClearHistoryMessage(satellite_id=satellite_id))
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
