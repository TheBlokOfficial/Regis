"""
Moduł obsługi strumieniowania odpowiedzi SSE z silnika LLM.
"""
import json
import time
import logging
from client.services.remote_tools_registry import RemoteToolsRegistry
from client.services.llm.service import llm_service


async def generate_chat_sse(message: str, system_prompt: str, history: list[dict], controller_url: str | None, room: str | None):
    """Generuje strumień SSE tokenów i zdarzeń ReAct z silnika LLM."""
    _start = time.perf_counter()
    ctrl_url = controller_url or llm_service.controller_url
    remote_tools = RemoteToolsRegistry(ctrl_url, room=room)

    response_text = ""
    try:
        if not llm_service.llm_engine:
            yield f"data: {json.dumps({'type': 'error', 'content': 'Silnik LLM nie jest zainicjalizowany.'})}\n\n"
            return

        async for event in llm_service.llm_engine.generate_response_stream(
            system_prompt=system_prompt,
            history=history,
            current_message=message,
            tools_registry=remote_tools
        ):
            if event["type"] == "content":
                response_text += event["content"]
            if event["type"] == "done":
                response_text = event["content"]

            yield f"data: {json.dumps(event)}\n\n"

        elapsed_ms = int((time.perf_counter() - _start) * 1000)
        yield f"data: {json.dumps({'type': 'done', 'content': response_text, 'elapsed_ms': elapsed_ms})}\n\n"

    except Exception as e:
        logging.exception("Błąd generacji odpowiedzi LLM w streaming.py")
        yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
