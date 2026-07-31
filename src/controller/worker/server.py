import asyncio
import json
import logging
import socket
import threading
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core import config
from controller.worker.node import WorkerNode
from core.remote_tools_registry import RemoteToolsRegistry

logging.basicConfig(level=logging.INFO)

# Globalne instancje — inicjalizowane w lifespan
worker_node: WorkerNode | None = None
_worker_id: str = ""
_controller_url: str = ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uruchamia Węzeł Roboczy i rejestruje go w Kontrolerze przy starcie.
    Wyrejestrowuje przy zatrzymaniu.
    """
    global worker_node, _worker_id, _controller_url

    settings = config.load_settings()

    active_tier = settings.get("active_tier", "butler")
    tier_config = {
        "butler": {"model": "qwen3:1.7b", "temperature": 0.1, "history_limit": 0},
        "regis":  {"model": "qwen3.5:9b",  "temperature": 0.1, "history_limit": 10},
    }
    tier_cfg = tier_config.get(active_tier, tier_config["butler"])

    worker_node = WorkerNode(
        model_name=settings.get("selected_model", tier_cfg["model"]),
        tier=active_tier,
        temperature=tier_cfg["temperature"],
        history_limit=tier_cfg.get("history_limit", settings.get("history_limit", 10))
    )

    # Parametry rejestracji
    _worker_id = settings.get("worker_id", f"worker-{socket.gethostname()}")
    _controller_url = settings.get("controller_url", "http://127.0.0.1:8000")
    
    if _controller_url == "auto":
        from core.discovery import discover_controller
        try:
            _controller_url = discover_controller()
        except Exception as e:
            logging.warning(f"Auto-Discovery zawiodło, używam fallbacku (http://127.0.0.1:8000). Błąd: {e}")
            _controller_url = "http://127.0.0.1:8000"

    worker_port = settings.get("worker_port", 8001)
    worker_host = settings.get("worker_host", "127.0.0.1")

    registration_payload = {
        "id": _worker_id,
        "host": worker_host,
        "port": worker_port,
        "model_name": settings.get("selected_model", tier_cfg["model"]),
        "tier": active_tier
    }

    try:
        resp = requests.post(
            f"{_controller_url}/v1/workers/register",
            json=registration_payload,
            timeout=5
        )
        if resp.ok:
            logging.info(f"Węzeł '{_worker_id}' zarejestrowany w Kontrolerze ({_controller_url}).")
        else:
            logging.warning(f"Rejestracja w Kontrolerze zwróciła {resp.status_code}. Kontynuuję.")
    except requests.RequestException as e:
        logging.warning(f"Nie udało się zarejestrować w Kontrolerze: {e}. Kontynuuję bez rejestracji.")

    async def _registration_loop():
        """W tle co 15 sekund odnawia rejestrację w Kontrolerze."""
        while True:
            await asyncio.sleep(15)
            try:
                await asyncio.to_thread(
                    requests.post,
                    f"{_controller_url}/v1/workers/register",
                    json=registration_payload,
                    timeout=5
                )
            except Exception:
                pass

    reg_task = asyncio.create_task(_registration_loop())

    logging.info(f"Węzeł Roboczy uruchomiony. Tier={active_tier}, Port={worker_port}")
    yield

    reg_task.cancel()

    # Wyrejestrowanie z Kontrolera przy zamknięciu
    try:
        requests.delete(f"{_controller_url}/v1/workers/{_worker_id}", timeout=5)
        logging.info(f"Węzeł '{_worker_id}' wyrejestrowany z Kontrolera.")
    except requests.RequestException as e:
        logging.warning(f"Nie udało się wyrejestrować z Kontrolera: {e}")

    # Zwalniamy model z VRAM
    if worker_node:
        worker_node.unload_model()

    logging.info("Węzeł Roboczy zatrzymany.")


app = FastAPI(lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str
    system_prompt: str = ""
    history: list[dict] = []
    controller_url: str = "http://127.0.0.1:8000"
    room: str | None = None  # kontekst pokoju Satelity — używany do inicjalizacji RemoteToolsRegistry


@app.get("/v1/health")
async def health():
    """Liveness check — zwraca stan węzła i informacje o modelu."""
    if not worker_node:
        return {"status": "starting"}
    return {
        "status": "ok",
        "worker_id": _worker_id,
        "model": worker_node.llm_engine.model_name,
        "tier": worker_node.llm_engine.tier
    }


@app.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """Przyjmuje wiadomość tekstową, zwraca odpowiedź modelu jako Server-Sent Events.

    Narzędzia są wykonywane przez Kontroler (RemoteToolsRegistry → HTTP POST /v1/tools/execute).
    """
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    tier = worker_node.llm_engine.tier
    remote_tools = RemoteToolsRegistry(request.controller_url, tier, room=request.room)

    def on_thought_token(chunk):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "thought", "content": chunk})

    def on_content_token(chunk):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": chunk})

    def on_tool_call(msg):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool", "content": msg})

    def on_raw_tool_call(data):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": data})

    def run_inference():
        from core.history_utils import build_messages_from_history
        try:
            # Budowa struktury messages przy użyciu utility
            messages = build_messages_from_history(
                system_prompt=request.system_prompt,
                history=request.history,
                current_message=request.message
            )

            response_text = worker_node.handle_chat(
                messages,
                remote_tools,
                on_tool_call=on_tool_call,
                on_thought_token=on_thought_token,
                on_content_token=on_content_token,
                on_raw_tool_call=on_raw_tool_call
            )
            loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": response_text})
        except Exception as e:
            logging.exception("Błąd generacji odpowiedzi")
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})

    thread = threading.Thread(target=run_inference)
    thread.start()

    async def event_generator():
        while True:
            item = await q.get()
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/v1/chat/audio_stream")
async def chat_audio_stream(
    file: UploadFile = File(...),
    controller_url: str = Form(default="http://127.0.0.1:8000"),
    system_prompt: str = Form(default=""),
    history: str = Form(default="[]")
):
    """Przyjmuje plik WAV, przepuszcza przez STT, a transkrypcję przez LLM. Zwraca SSE."""
    audio_bytes = await file.read()

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    tier = worker_node.llm_engine.tier
    remote_tools = RemoteToolsRegistry(controller_url, tier, room=None)

    def on_stt_result(text):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "stt_result", "content": text})

    def on_thought_token(chunk):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "thought", "content": chunk})

    def on_content_token(chunk):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": chunk})

    def on_tool_call(msg):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool", "content": msg})

    def on_raw_tool_call(data):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": data})

    def run_inference():
        try:
            parsed_history = json.loads(history)
            
            response_text = worker_node.handle_audio(
                audio_bytes,
                remote_tools,
                system_prompt=system_prompt,
                history=parsed_history,
                on_stt_result=on_stt_result,
                on_tool_call=on_tool_call,
                on_thought_token=on_thought_token,
                on_content_token=on_content_token,
                on_raw_tool_call=on_raw_tool_call
            )
            if response_text == "Nie rozpoznano żadnego tekstu ze strumienia audio.":
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": response_text})
            else:
                loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": response_text})
        except Exception as e:
            logging.exception("Błąd generacji odpowiedzi z audio")
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})

    thread = threading.Thread(target=run_inference)
    thread.start()

    async def event_generator():
        while True:
            item = await q.get()
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                break

    return StreamingResponse(event_generator(), media_type="text/event-stream")




@app.post("/v1/clear_history")
async def clear_history():
    """Resetuje historię konwersacji węzła."""
    if worker_node:
        worker_node.clear_history()
    return {"status": "ok"}
