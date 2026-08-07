import asyncio
import json
import httpx
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import JSONResponse, StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import threading

import client.controller_api as controller_api
import client.service_bus as service_bus

app = FastAPI(title="Regis Client Internal Proxy")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    """Inicjalizuje magistralę komend usług przy starcie proxy."""
    service_bus.init(asyncio.get_event_loop())


@app.post("/internal/wake_check")
async def wake_check():
    """Wysyła request przez WebSocket do Kontrolera o pozwolenie na nagrywanie."""
    permitted = await controller_api.request_wake_permission(timeout=2.0)
    if permitted:
        return {"permitted": True}
    else:
        return JSONResponse(status_code=503, content={"permitted": False, "reason": "Kontroler odmówił dostępu lub brak workerów."})


@app.get("/internal/service_commands")
@app.get("/internal/satellite_commands")  # Alias dla wstecznej kompatybilności
async def service_commands_stream():
    """
    SSE endpoint – usługi podłączone lokalnie (np. Satelita) subskrybują ten strumień,
    aby odbierać przychodzące komendy od Kontrolera przesyłane przez magistralę komend.
    """
    async def generate():
        while True:
            cmd = await service_bus.get_command()
            if cmd is not None:
                yield f"data: {json.dumps(cmd)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/internal/audio_complete")
async def audio_complete():
    """
    Satelita wywołuje ten endpoint po zakończeniu odtwarzania audio.
    Proxy informuje Kontroler przez WebSocket.
    """
    controller_api.send_audio_complete()
    return {"ok": True}


@app.post("/internal/task_event")
async def task_event(request: Request):
    """
    Usługi podrzędne (llm, audio) odsyłają tu wyniki/ramki zdarzeń.
    Proxy przekazuje je do Kontrolera przez WebSocket.
    """
    data = await request.json()
    task_id = data.get("task_id")
    event = data.get("event")
    if task_id and event:
        controller_api.send_task_result(task_id, event)
    return {"ok": True}


@app.post("/internal/tool_execute")
async def proxy_tool_execute(request: Request):
    """
    Przekazuje wywołanie narzędzia z podprocesu do Kontrolera.
    """
    data = await request.json()
    controller_url = controller_api.get_controller_url()
    target_url = f"{controller_url}/v1/tools/execute"

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(target_url, json=data)
            return Response(content=resp.content, status_code=resp.status_code, media_type="application/json")
        except Exception as e:
            return JSONResponse(status_code=500, content={"error": f"Błąd proxy narzędzia: {e}"})


@app.post("/internal/audio")
async def proxy_audio(request: Request, file: UploadFile = File(...)):
    """
    Przekazuje plik WAV do Kontrolera z dołączonym X-Client-ID.
    Zwraca strumień SSE z informacyjnymi zdarzeniami (transkrypcja, narzędzia itp.).
    """
    client_id = controller_api._get_client_id()
    controller_url = controller_api.get_controller_url()

    target_url = f"{controller_url}/v1/chat/audio_stream"
    headers = {"X-Client-ID": client_id}

    file_content = await file.read()

    async def stream_generator():
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {"file": (file.filename, file_content, file.content_type)}
            async with client.stream("POST", target_url, headers=headers, files=files) as response:
                if response.status_code != 200:
                    yield f"event: error\ndata: {response.status_code}\n\n"
                    return
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(stream_generator(), media_type="text/event-stream")


def run_internal_proxy(port: int = 47831):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


def start_internal_proxy_thread():
    thread = threading.Thread(target=run_internal_proxy, daemon=True)
    thread.start()
    return thread
