import asyncio

from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from worker.registration import registration_manager
from worker.service import inference_service

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    system_prompt: str = ""
    history: list[dict] = []
    controller_url: str = "http://127.0.0.1:8000"
    room: str | None = None


@router.get("/v1/health")
async def health():
    if not inference_service.worker_node:
        return {"status": "starting"}
    try:
        engine = inference_service.worker_node.llm_engine
        model_name = getattr(engine.backend, "model_name", "nieznany")
        return {
            "status": "ok",
            "worker_id": registration_manager.worker_id,
            "model": model_name
        }
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@router.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    inference_service.run_chat_stream(
        message=request.message,
        system_prompt=request.system_prompt,
        history=request.history,
        controller_url=request.controller_url,
        room=request.room,
        q=q,
        loop=loop
    )

    return StreamingResponse(inference_service.stream_events(q), media_type="text/event-stream")


@router.post("/v1/chat/audio_stream")
async def chat_audio_stream(
    file: UploadFile = File(...),
    controller_url: str = Form(default="http://127.0.0.1:8000"),
    system_prompt: str = Form(default=""),
    history: str = Form(default="[]")
):
    audio_bytes = await file.read()
    loop = asyncio.get_event_loop()
    q: asyncio.Queue = asyncio.Queue()

    inference_service.run_audio_stream(
        audio_bytes=audio_bytes,
        system_prompt=system_prompt,
        history_json=history,
        controller_url=controller_url,
        q=q,
        loop=loop
    )

    return StreamingResponse(inference_service.stream_events(q), media_type="text/event-stream")


@router.post("/v1/clear_history")
async def clear_history():
    inference_service.clear_history()
    return {"status": "ok"}
