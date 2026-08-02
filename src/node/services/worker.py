import asyncio
import json
import logging
import socket
import time
import argparse
import io
import sys
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from node import config
from node.services.remote_tools_registry import RemoteToolsRegistry
from node.engines.llm_engine import LLMEngine
from node.engines.stt_engine import STTEngine
from node.engines.tts_engine import TTSEngine
from node.logger import setup_logging

setup_logging("node_worker")

# Globalne instancje — inicjalizowane w lifespan
llm_engine: LLMEngine | None = None
stt_engine: STTEngine | None = None
tts_engine: TTSEngine | None = None

_worker_id: str = ""
_controller_url: str = ""
_worker_port: int = 8001
_selected_model: str = "qwen3.5:9b"

def get_args():
    parser = argparse.ArgumentParser(description="Regis Worker Service")
    parser.add_argument("--model", type=str, default=None, help="LLM Model to use")
    parser.add_argument("--port", type=int, default=None, help="Worker port")
    parser.add_argument("--controller-url", type=str, default=None, help="Controller URL")
    # Zwraca puste args dla trybu pytest/innych wywołań
    return parser.parse_known_args()[0]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uruchamia Węzeł Roboczy i rejestruje go w Kontrolerze przy starcie."""
    global llm_engine, stt_engine, tts_engine, _worker_id, _controller_url, _worker_port, _selected_model

    args = get_args()
    settings = config.load_settings()

    _selected_model = args.model or settings.get("selected_model", "qwen3.5:4b")
    _worker_port = args.port or settings.get("worker_port", 8001)
    worker_priority = int(settings.get("worker_priority", 100))
    _controller_url_setting = args.controller_url or settings.get("controller_url", "http://127.0.0.1:8000")

    llm_engine = LLMEngine(model_name=_selected_model, temperature=0.1)

    try:
        await llm_engine.preload_model()
    except Exception as e:
        logging.error(f"Nie można uruchomić Workera - model niedostępny: {e}")
        import os
        os._exit(1)

    # Parametry rejestracji
    _worker_id = settings.get("worker_id", settings.get("instance_name", f"worker-{socket.gethostname()}"))
    
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

    from core.discovery import get_local_ip
    worker_host = settings.get("worker_host", get_local_ip())
    registration_host = get_local_ip() if worker_host == "0.0.0.0" else worker_host

    registration_payload = {
        "id": _worker_id,
        "host": registration_host,
        "port": _worker_port,
        "model_name": _selected_model,
        "priority": worker_priority
    }

    try:
        resp = requests.post(f"{_controller_url}/v1/workers/register", json=registration_payload, timeout=5)
        if resp.ok:
            logging.info(f"Węzeł '{_worker_id}' zarejestrowany w Kontrolerze ({_controller_url}).")
    except requests.RequestException as e:
        logging.warning(f"Brak rejestracji w Kontrolerze: {e}.")

    async def _registration_loop():
        failures = 0
        while True:
            await asyncio.sleep(15)
            try:
                resp = await asyncio.to_thread(requests.post, f"{_controller_url}/v1/workers/register", json=registration_payload, timeout=5)
                if resp.ok:
                    if failures > 0:
                        logging.info("Odnawiono połączenie.")
                    failures = 0
                else:
                    failures += 1
            except Exception:
                failures += 1
            
            if failures >= 2 and _controller_url_setting == "auto":
                await asyncio.to_thread(_resolve_controller)

    reg_task = asyncio.create_task(_registration_loop())
    logging.info(f"Węzeł Roboczy uruchomiony. Model={_selected_model}, Port={_worker_port}")
    
    yield

    reg_task.cancel()
    try:
        requests.delete(f"{_controller_url}/v1/workers/{_worker_id}", timeout=2)
    except requests.RequestException:
        pass

    if llm_engine:
        await llm_engine.unload_model()


app = FastAPI(lifespan=lifespan)

class ChatRequest(BaseModel):
    message: str
    system_prompt: str = ""
    history: list[dict] = []
    controller_url: str | None = None
    room: str | None = None  


@app.get("/v1/health")
async def health():
    if not llm_engine:
        return {"status": "starting"}
    return {
        "status": "ok",
        "worker_id": _worker_id,
        "model": _selected_model
    }


@app.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """Asynchroniczny generator SSE dla czatu tekstowego."""
    _start = time.perf_counter()
    ctrl_url = request.controller_url or _controller_url
    remote_tools = RemoteToolsRegistry(ctrl_url, room=request.room)

    async def _stream():
        response_text = ""
        try:
            async for event in llm_engine.generate_response_stream(
                system_prompt=request.system_prompt,
                history=request.history,
                current_message=request.message,
                tools_registry=remote_tools
            ):
                if event["type"] == "content":
                    response_text += event["content"]
                if event["type"] == "done":
                    response_text = event["content"]
                    
                yield f"data: {json.dumps(event)}\n\n"
            
            # Po pętli LLM - TTS
            elapsed_ms = int((time.perf_counter() - _start) * 1000)
            
            global tts_engine
            if tts_engine is None:
                tts_engine = TTSEngine(model_name="pl_PL-darkman-medium")
                
            b64_audio = await asyncio.to_thread(tts_engine.synthesize_to_base64, response_text)
            if b64_audio:
                yield f"data: {json.dumps({'type': 'tts_audio', 'content': b64_audio})}\n\n"
                
            yield f"data: {json.dumps({'type': 'done', 'content': response_text, 'elapsed_ms': elapsed_ms})}\n\n"
            
        except Exception as e:
            logging.exception("Błąd generacji odpowiedzi")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/v1/chat/audio_stream")
async def chat_audio_stream(
    file: UploadFile = File(...),
    controller_url: str = Form(default="http://127.0.0.1:8000"),
    system_prompt: str = Form(default=""),
    history: str = Form(default="[]"),
    room: str | None = Form(default=None)
):
    """Przepuszcza audio przez STT -> LLM -> TTS."""
    _start = time.perf_counter()
    audio_bytes = await file.read()
    
    ctrl_url = controller_url or _controller_url
    remote_tools = RemoteToolsRegistry(ctrl_url, room=room)
    parsed_history = json.loads(history)

    async def _stream():
        try:
            global stt_engine
            if stt_engine is None:
                stt_engine = STTEngine(model_size="small", language="pl")
                
            audio_io = io.BytesIO(audio_bytes)
            stt_start = time.perf_counter()
            text = await asyncio.to_thread(stt_engine.transcribe_audio_file, audio_io)
            stt_elapsed = time.perf_counter() - stt_start
            
            yield f"data: {json.dumps({'type': 'profiler', 'content': {'metric': 'stt', 'value': int(stt_elapsed * 1000)}})}\n\n"

            if not text:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Nie rozpoznano żadnego tekstu ze strumienia audio.'})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'stt_result', 'content': text})}\n\n"

            response_text = ""
            async for event in llm_engine.generate_response_stream(
                system_prompt=system_prompt,
                history=parsed_history,
                current_message=text,
                tools_registry=remote_tools
            ):
                if event["type"] == "content":
                    response_text += event["content"]
                if event["type"] == "done":
                    response_text = event["content"]
                yield f"data: {json.dumps(event)}\n\n"

            elapsed_ms = int((time.perf_counter() - _start) * 1000)
            
            global tts_engine
            if tts_engine is None:
                tts_engine = TTSEngine(model_name="pl_PL-darkman-medium")
                
            b64_audio = await asyncio.to_thread(tts_engine.synthesize_to_base64, response_text)
            if b64_audio:
                yield f"data: {json.dumps({'type': 'tts_audio', 'content': b64_audio})}\n\n"
                
            yield f"data: {json.dumps({'type': 'done', 'content': response_text, 'elapsed_ms': elapsed_ms})}\n\n"

        except Exception as e:
            logging.exception("Błąd pipeline'u audio")
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/v1/clear_history")
async def clear_history():
    return {"status": "ok"}

@app.post("/v1/system/shutdown")
async def system_shutdown():
    if llm_engine:
        await llm_engine.unload_model()
    try:
        requests.delete(f"{_controller_url}/v1/workers/{_worker_id}", timeout=2)
    except Exception:
        pass
    return {"status": "shutting_down"}

if __name__ == "__main__":
    import uvicorn
    args = get_args()
    port = args.port or 8001
    uvicorn.run(app, host="0.0.0.0", port=port)
