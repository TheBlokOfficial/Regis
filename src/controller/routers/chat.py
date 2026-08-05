import asyncio
import json
import threading

from fastapi import APIRouter, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import controller.providers as providers
import controller.registry as registry
from controller.services.chat_service import proxy_sse_to_queue, clear_conversation_history

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

    controller_url = registry._settings_cache.get("controller_url", "auto")
    if controller_url == "auto" or "127.0.0.1" in controller_url or "localhost" in controller_url:
        from protocol.discovery import get_local_ip
        controller_url = f"http://{get_local_ip()}:8000"

    room = request.room
    if not room and request.satellite_id and request.satellite_id in registry.satellite_registry:
        room = registry.satellite_registry[request.satellite_id].get("room")

    payload = {"message": request.message, "controller_url": controller_url, "room": room}

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    thread = threading.Thread(target=proxy_sse_to_queue, args=(payload, q, loop, False, None))
    thread.start()

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
    if client_id and client_id in registry.node_registry:
        services = registry.node_registry[client_id].get("services", {})
        if "satellite" in services:
            room = services["satellite"].get("room")

    audio_bytes = await file.read()
    controller_url = registry._settings_cache.get("controller_url", "auto")
    if controller_url == "auto" or "127.0.0.1" in controller_url or "localhost" in controller_url:
        from protocol.discovery import get_local_ip
        controller_url = f"http://{get_local_ip()}:8000"

    payload = {"controller_url": controller_url}
    if room:
        payload["room"] = room

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    thread = threading.Thread(target=proxy_sse_to_queue, args=(payload, q, loop, True, audio_bytes))
    thread.start()

    has_tts = False

    async def event_generator():
        nonlocal has_tts
        while True:
            item = await q.get()
            if item["type"] == "tts_audio":
                has_tts = True
                if client_id:
                    await registry.node_manager.send_command(
                        client_id, "play_audio", {"audio_b64": item.get("content", "")}
                    )
                continue  # Nie przepuszczaj tts_audio przez SSE
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                if not has_tts and client_id:
                    await registry.node_manager.send_command(client_id, "service_control", {"action": "resume"})
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
    history = registry.get_session_history(satellite_id)
    return {"satellite_id": satellite_id or "default", "history": history}


@router_chat.get("/v1/sessions")
async def get_sessions():
    """Zwraca listę aktywnych sesji konwersacji."""
    active_sessions = []
    for sid, turns in registry.conversation_sessions.items():
        last_t = registry.session_last_interaction_times.get(sid, 0.0)
        active_sessions.append({
            "id": sid,
            "turns_count": len(turns),
            "last_interaction": last_t
        })
    return {"sessions": active_sessions}


@router_chat.get("/v1/rooms")
async def get_rooms():
    from controller import config
    rooms_data = config.load_rooms()
    return {"rooms": list(rooms_data.keys())}
