"""
Moduł tras API dla usługi LLM Worker.
"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from client.services.llm.service import llm_service
from client.services.llm.registration import registration_manager
from client.services.llm.streaming import generate_chat_sse

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    system_prompt: str = ""
    history: list[dict] = []
    controller_url: str | None = None
    room: str | None = None


@router.get("/v1/health")
async def health():
    if not llm_service.llm_engine:
        return {"status": "starting"}
    return {
        "status": "ok",
        "service": "llm",
        "node_id": llm_service.node_id,
        "model": llm_service.selected_model
    }


@router.post("/v1/chat/stream")
async def chat_stream(request: ChatRequest):
    """Asynchroniczny generator SSE dla czatu tekstowego i rozumowania LLM."""
    return StreamingResponse(
        generate_chat_sse(
            message=request.message,
            system_prompt=request.system_prompt,
            history=request.history,
            controller_url=request.controller_url,
            room=request.room
        ),
        media_type="text/event-stream"
    )


@router.post("/v1/clear_history")
async def clear_history():
    return {"status": "ok"}


@router.post("/v1/system/shutdown")
async def system_shutdown():
    registration_manager.stop_registration()
    await llm_service.stop_engine()
    return {"status": "shutting_down"}
