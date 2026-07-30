import asyncio
import json
import logging
import threading
import datetime
import os

import requests
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

import controller.registry as registry
from controller.registry import _TIER_PRIORITY

router_chat = APIRouter()


def _build_system_prompt(tier: str, room: str | None = None) -> str:
    from core import config
    tier_path = os.path.join(config.CONFIG_DIR, "prompts", f"tier_{tier}.md")
    tier_prompt = "Jesteś asystentem domowym."
    try:
        with open(tier_path, "r", encoding="utf-8") as f:
            tier_prompt = f.read().strip()
    except Exception as e:
        logging.warning(f"Błąd ładowania {tier_path}: {e}")
        
    global_menu = ""
    if registry.tools_registry:
        global_menu = registry.tools_registry.get_global_menu()
        
    room_context = f"\n\nOBECNY POKÓJ: {room}" if room else ""
        
    if tier == "butler":
        return f"{tier_prompt}\n\n{global_menu}{room_context}"

    from core.schemas import render_tools_for_prompt
    tools_text = render_tools_for_prompt(tier)
    
    return f"{tools_text}\n\n{global_menu}{room_context}\n\n{tier_prompt}"


class ChatRequest(BaseModel):
    message: str
    satellite_id: str | None = None
    room: str | None = None


def _proxy_sse_to_queue(base_payload: dict, q: asyncio.Queue, loop: asyncio.AbstractEventLoop, is_audio: bool = False, audio_bytes: bytes = None):
    """Pomocnik: odczytuje SSE z Workerów (z Failoverem) i umieszcza eventy w asyncio.Queue."""
    import time
    registry.last_interaction_time = time.time()
    
    workers = sorted(list(registry.worker_registry.values()), key=lambda w: _TIER_PRIORITY.get(w["tier"], 0), reverse=True)
    if not workers:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Brak dostępnych węzłów w rejestrze."})
        return

    success = False
    for worker in workers:
        worker_id = worker["id"]
        tier = worker.get("tier", "butler")
        room = base_payload.get("room")
        
        system_prompt = _build_system_prompt(tier, room=room)
        
        if not is_audio:
            worker_url = f"{worker['base_url']}/v1/chat/stream"
            payload = dict(base_payload)
            payload["system_prompt"] = system_prompt
            payload["history"] = registry.conversation_history
        else:
            worker_url = f"{worker['base_url']}/v1/chat/audio_stream"
        
        logging.info(f"Routowanie żądania do węzła: {worker_id}")
        
        routing_event = {
            "type": "routing_info",
            "worker_id": worker["id"],
            "model": worker.get("model_name", "nieznany"),
            "tier": tier,
        }
        loop.call_soon_threadsafe(q.put_nowait, routing_event)

        final_content = ""
        stt_content = ""

        used_tools_logs = []
        
        try:
            if not is_audio:
                resp = requests.post(worker_url, json=payload, stream=True, timeout=(1.0, 300.0))
            else:
                files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
                data = dict(base_payload)
                data["system_prompt"] = system_prompt
                data["history"] = json.dumps(registry.conversation_history)
                resp = requests.post(worker_url, files=files, data=data, stream=True, timeout=(1.0, 300.0))
                
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "stt_result":
                            stt_content = event.get("content", "")
                        elif event.get("type") == "tool_call_raw":
                            used_tools_logs.append(event.get("content"))
                        elif event.get("type") == "done":
                            final_content = event.get("content", "")
                            
                        loop.call_soon_threadsafe(q.put_nowait, event)
                        if event.get("type") in ("done", "error"):
                            success = True
                            break
                    except json.JSONDecodeError:
                        pass
            
            if success and final_content:
                user_msg = stt_content if is_audio else base_payload.get("message", "")
                if user_msg and final_content != "Przerwano zapytanie. Przekroczono maksymalną liczbę wywołań narzędzi (timeout pętli ReAct).":
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    registry.conversation_history.append({
                        "user": user_msg,
                        "assistant": final_content,
                        "tools": used_tools_logs,
                        "timestamp": now
                    })
                    from core import config
                    limit = config.load_settings().get("history_limit", 3)
                    if limit <= 0:
                        registry.conversation_history.clear()
                    elif len(registry.conversation_history) > limit:
                        del registry.conversation_history[:-limit]
            
            success = True
            break
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError):
            logging.warning(f"Węzeł {worker_id} nie odpowiada (Connect błąd). Usuwam z rejestru.")
            if worker_id in registry.worker_registry:
                del registry.worker_registry[worker_id]
        except Exception as e:
            logging.exception(f"Inny błąd proxy do węzła {worker_id}")
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})
            return

    if not success:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Wszystkie dostępne węzły zawiodły."})


@router_chat.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    if not registry.worker_registry:
        return JSONResponse(
            {"error": "Błąd Krytyczny: Brak Węzłów. Awaryjny węzeł na Malince (Butler) nie zgłosił gotowości. Sprawdź status regis-worker.service."},
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

    thread = threading.Thread(target=_proxy_sse_to_queue, args=(payload, q, loop, False, None))
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
    if not registry.worker_registry:
        return JSONResponse(
            {"error": "Błąd Krytyczny: Brak Węzłów. Awaryjny węzeł na Malince (Butler) nie zgłosił gotowości. Sprawdź status regis-worker.service."},
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

    thread = threading.Thread(target=_proxy_sse_to_queue, args=(payload, q, loop, True, audio_bytes))
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
    registry.conversation_history.clear()
    
    # Wywołanie legacy na Workerach (na wszelki wypadek)
    for worker in list(registry.worker_registry.values()):
        try:
            requests.post(f"{worker['base_url']}/v1/clear_history", timeout=2)
        except:
            pass
            
    return {"status": "ok"}


@router_chat.get("/v1/rooms")
async def get_rooms():
    from core import config
    rooms_data = config.load_rooms()
    return {"rooms": list(rooms_data.keys())}
