import asyncio
import json
import logging
import socket
import threading
import time
from contextlib import asynccontextmanager
import datetime

import requests
from fastapi import FastAPI, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from node import config
from node.node import WorkerNode
from node.remote_tools_registry import RemoteToolsRegistry

from node.logger import setup_logging
setup_logging("node")

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

    worker_priority = int(settings.get("worker_priority", 100))
    selected_model = settings.get("selected_model", "qwen3.5:4b")

    worker_node = WorkerNode(
        model_name=selected_model,
        temperature=0.1
    )

    try:
        worker_node.preload_model()
    except Exception as e:
        logging.error(f"Nie można uruchomić Węzła - Ollama jest niedostępna lub zwróciła błąd: {e}")
        import os
        os._exit(1)

    # Parametry rejestracji
    _worker_id = settings.get("worker_id", settings.get("instance_name", f"worker-{socket.gethostname()}"))
    _controller_url_setting = settings.get("controller_url", "http://127.0.0.1:8000")
    
    def _resolve_controller():
        global _controller_url
        if _controller_url_setting == "auto":
            from core.discovery import discover_controller
            try:
                _controller_url = discover_controller()
            except Exception as e:
                logging.warning(f"Auto-Discovery zawiodło: {e}. Używam localhost.")
                _controller_url = "http://127.0.0.1:8000"
        else:
            _controller_url = _controller_url_setting

    _resolve_controller()

    worker_port = settings.get("worker_port", 8001)
    from core.discovery import get_local_ip
    worker_host = settings.get("worker_host", get_local_ip())

    registration_host = get_local_ip() if worker_host == "0.0.0.0" else worker_host

    registration_payload = {
        "id": _worker_id,
        "host": registration_host,
        "port": worker_port,
        "model_name": selected_model,
        "priority": worker_priority
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
        failures = 0
        while True:
            await asyncio.sleep(15)
            try:
                resp = await asyncio.to_thread(
                    requests.post,
                    f"{_controller_url}/v1/workers/register",
                    json=registration_payload,
                    timeout=5
                )
                if resp.ok:
                    if failures > 0:
                        logging.info(f"Pomyślnie odnowiono połączenie i rejestrację w Kontrolerze ({_controller_url}).")
                    failures = 0
                else:
                    failures += 1
            except Exception as e:
                if failures == 0:
                    logging.warning(f"Utracono połączenie z Kontrolerem: {e}")
                failures += 1
            
            if failures >= 2 and _controller_url_setting == "auto":
                logging.info(f"Ponawiam próbę Auto-Discovery (błędy: {failures})...")
                await asyncio.to_thread(_resolve_controller)

    reg_task = asyncio.create_task(_registration_loop())

    logging.info(f"Węzeł Roboczy uruchomiony. Priority={worker_priority}, Port={worker_port}")
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
    controller_url: str | None = None
    room: str | None = None  


async def _stream_events(q: asyncio.Queue):
    while True:
        item = await q.get()
        yield f"data: {json.dumps(item)}\n\n"
        if item["type"] in ("done", "error"):
            break


@app.get("/v1/health")
async def health():
    """Liveness check — zwraca stan węzła i informacje o modelu."""
    if not worker_node:
        return {"status": "starting"}
    try:
        engine = worker_node.llm_engine
        model_name = getattr(engine.backend, "model_name", "nieznany")
        return {
            "status": "ok",
            "worker_id": _worker_id,
            "model": model_name
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """Przyjmuje wiadomość tekstową oraz strukturę z Kontrolera. Zwraca odpowiedź jako SSE."""
    _start = time.perf_counter()
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    ctrl_url = request.controller_url or _controller_url
    remote_tools = RemoteToolsRegistry(ctrl_url, room=request.room)

    def on_thought_token(chunk):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "thought", "content": chunk})

    def on_content_token(chunk):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": chunk})

    def on_tool_call(msg):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": msg})

    def on_raw_tool_call(data):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_dict", "content": data})

    def on_profiler(metric_data):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "profiler", "content": metric_data})

    def run_inference():
        from node.history_utils import build_messages_from_history
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
                on_raw_tool_call=on_raw_tool_call,
                on_profiler=on_profiler
            )
            elapsed_ms = int((time.perf_counter() - _start) * 1000)
            
            b64_audio = worker_node.tts_engine.synthesize_to_base64(response_text)
            if b64_audio:
                loop.call_soon_threadsafe(q.put_nowait, {"type": "tts_audio", "content": b64_audio})
                
            loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": response_text, "elapsed_ms": elapsed_ms})
        except Exception as e:
            logging.exception("Błąd generacji odpowiedzi")
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})

    thread = threading.Thread(target=run_inference)
    thread.start()

    return StreamingResponse(_stream_events(q), media_type="text/event-stream")





@app.post("/v1/chat/audio_stream")
async def chat_audio_stream(
    file: UploadFile = File(...),
    controller_url: str = Form(default="http://127.0.0.1:8000"),
    system_prompt: str = Form(default=""),
    history: str = Form(default="[]"),
    room: str | None = Form(default=None)
):
    """Przyjmuje plik WAV, przepuszcza przez STT, a transkrypcję przez LLM. Zwraca SSE."""
    _start = time.perf_counter()
    
    audio_bytes = await file.read()

    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    ctrl_url = controller_url or _controller_url
    remote_tools = RemoteToolsRegistry(ctrl_url, room=room)

    def on_stt_result(text):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "stt_result", "content": text})

    def on_thought_token(chunk):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "thought", "content": chunk})

    def on_content_token(chunk):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": chunk})

    def on_tool_call(msg):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": msg})

    def on_raw_tool_call(data):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_dict", "content": data})
        
    def on_profiler(metric_data):
        loop.call_soon_threadsafe(q.put_nowait, {"type": "profiler", "content": metric_data})

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
                on_raw_tool_call=on_raw_tool_call,
                on_profiler=on_profiler
            )
            
            elapsed_ms = int((time.perf_counter() - _start) * 1000)
            
            if response_text == "Nie rozpoznano żadnego tekstu ze strumienia audio.":
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": response_text})
            else:
                b64_audio = worker_node.tts_engine.synthesize_to_base64(response_text)
                if b64_audio:
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "tts_audio", "content": b64_audio})
                    
                loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": response_text, "elapsed_ms": elapsed_ms})
        except Exception as e:
            logging.exception("Błąd generacji odpowiedzi z audio")
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})

    thread = threading.Thread(target=run_inference)
    thread.start()

    return StreamingResponse(_stream_events(q), media_type="text/event-stream")


@app.post("/v1/clear_history")
async def clear_history():
    """Legacy endpoint. Kontroler sam czyści historię, ale może go profilaktycznie wołać."""
    return {"status": "ok"}

@app.post("/v1/system/shutdown")
async def system_shutdown():
    if worker_node:
        worker_node.unload_model()
    try:
        requests.delete(f"{_controller_url}/v1/workers/{_worker_id}", timeout=2)
    except Exception:
        pass
    return {"status": "shutting_down"}
