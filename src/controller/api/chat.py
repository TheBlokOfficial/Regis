import asyncio
import json

from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import controller.llm.providers as providers
import controller.core.app_state as app_state
import controller.core.client_store as client_store
import controller.core.session_store as session_store
from controller.llm.orchestrator import proxy_sse_to_queue, clear_conversation_history

router_chat = APIRouter()


class ChatRequest(BaseModel):
    message: str
    satellite_id: str | None = None
    room: str | None = None


@router_chat.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    if not providers.has_llm_provider():
        return JSONResponse(
            {"error": "Brak dostępnego providera LLM."},
            status_code=503
        )

    controller_url = app_state._settings_cache.get("controller_url", "auto")
    if controller_url == "auto" or "127.0.0.1" in controller_url or "localhost" in controller_url:
        from protocol.discovery import get_local_ip
        controller_url = f"http://{get_local_ip()}:8000"

    room = request.room
    if not room and request.satellite_id and request.satellite_id in client_store.client_registry:
        services = client_store.client_registry[request.satellite_id].get("services", {})
        if isinstance(services, dict) and "satellite" in services:
            room = services["satellite"].get("room")

    payload = {"message": request.message, "controller_url": controller_url, "room": room}

    q: asyncio.Queue = asyncio.Queue()

    asyncio.create_task(proxy_sse_to_queue(payload, q, is_audio=False, audio_bytes=None))

    async def event_generator():
        while True:
            item = await q.get()
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router_chat.post("/v1/chat/audio_stream")
async def chat_audio_stream(
    request: Request,
    file: UploadFile = File(...)
):
    if not providers.has_llm_provider():
        return JSONResponse(
            {"error": "Brak dostępnego providera LLM."},
            status_code=503
        )

    client_id = request.headers.get("X-Client-ID")
    room = None
    if client_id and client_id in client_store.client_registry:
        services = client_store.client_registry[client_id].get("services", {})
        if isinstance(services, dict) and "satellite" in services:
            room = services["satellite"].get("room")

    audio_bytes = await file.read()
    controller_url = app_state._settings_cache.get("controller_url", "auto")
    if controller_url == "auto" or "127.0.0.1" in controller_url or "localhost" in controller_url:
        from protocol.discovery import get_local_ip
        controller_url = f"http://{get_local_ip()}:8000"

    payload = {"controller_url": controller_url}
    if room:
        payload["room"] = room

    q: asyncio.Queue = asyncio.Queue()

    asyncio.create_task(proxy_sse_to_queue(payload, q, is_audio=True, audio_bytes=audio_bytes))

    has_tts = False

    async def event_generator():
        nonlocal has_tts
        while True:
            item = await q.get()
            if item["type"] == "tts_audio":
                has_tts = True
                if client_id:
                    from controller.core.connection_manager import client_manager
                    await client_manager.send_command(
                        client_id, "play_audio", {"audio_b64": item.get("content", "")}
                    )
                continue  # Nie przepuszczaj tts_audio przez SSE
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                if not has_tts and client_id:
                    from controller.core.connection_manager import client_manager
                    await client_manager.send_command(client_id, "satellite_control", {"action": "resume"})
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router_chat.post("/v1/clear_history")
async def clear_history(satellite_id: str | None = None):
    """Resetuje historię konwersacji (danej sesji lub wszystkich) w pamięci Kontrolera."""
    clear_conversation_history(satellite_id)
    return {"status": "ok"}


@router_chat.get("/v1/chat/history")
async def get_history(satellite_id: str | None = None):
    """Zwraca historię konwersacji dla wybranej Satelity / sesji."""
    history = session_store.get_session_history(satellite_id)
    return {"satellite_id": satellite_id or "default", "history": history}


@router_chat.get("/v1/sessions")
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


@router_chat.get("/v1/rooms")
async def get_rooms():
    from controller.config import loader as config
    from controller.config.schemas import RoomsConfig
    rooms_data = config.load(RoomsConfig).root
    return {"rooms": list(rooms_data.keys())}
