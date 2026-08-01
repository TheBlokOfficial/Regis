import asyncio
import json
import threading

from fastapi import APIRouter, UploadFile, File, Form
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
        from core.discovery import get_local_ip
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
    file: UploadFile = File(...),
    room: str | None = Form(default=None),
    satellite_id: str | None = Form(default=None)
):
    if not providers.has_llm_provider():
        return JSONResponse(
            {"error": "Brak dostępnego providera LLM."},
            status_code=503
        )

    audio_bytes = await file.read()
    controller_url = registry._settings_cache.get("controller_url", "auto")
    if controller_url == "auto" or "127.0.0.1" in controller_url or "localhost" in controller_url:
        from core.discovery import get_local_ip
        controller_url = f"http://{get_local_ip()}:8000"

    if not room and satellite_id and satellite_id in registry.satellite_registry:
        room = registry.satellite_registry[satellite_id].get("room")

    payload = {"controller_url": controller_url}
    if room:
        payload["room"] = room

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    thread = threading.Thread(target=proxy_sse_to_queue, args=(payload, q, loop, True, audio_bytes))
    thread.start()

    async def event_generator():
        while True:
            item = await q.get()
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router_chat.post("/v1/clear_history")
async def clear_history():
    """Resetuje historię konwersacji w pamięci Kontrolera."""
    clear_conversation_history()
    return {"status": "ok"}


@router_chat.get("/v1/rooms")
async def get_rooms():
    from core import config
    rooms_data = config.load_rooms()
    return {"rooms": list(rooms_data.keys())}
