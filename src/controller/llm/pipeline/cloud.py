"""
Pipeline chmurowy — bezpośrednie wywołanie backendu LLM (np. OpenRouter) na Kontrolerze.

Obsługuje wyłącznie żądania tekstowe (nie audio).
Strumieniuje tokeny do asyncio.Queue, którą konsumuje endpoint SSE.
"""
import asyncio
import logging
import time

import controller.core.app_state as app_state
from controller.llm.prompt.builder import build_system_prompt
from controller.llm.session.history import build_messages_from_history
from controller.llm.pipeline.session_manager import save_and_publish, build_turn

logger = logging.getLogger(__name__)


async def run_cloud_pipeline(
    payload: dict,
    backend,
    session_history: list[dict],
    q: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
) -> None:
    """
    Wykonuje przebieg konwersacji z bezpośrednim wywołaniem backendu chmurowego.

    Args:
        payload: Słownik żądania zawierający pola: message, room, satellite_id.
        backend: Instancja LLMBackend (np. OpenRouterBackend).
        session_history: Historia sesji do przekazania modelowi.
        q: Kolejka eventów SSE — tokeny i status są tu umieszczane.
        loop: Pętla zdarzeń asyncio — używana do thread-safe put_nowait.
    """
    satellite_id = payload.get("satellite_id") or "web_ui"
    room = payload.get("room")
    user_message = payload.get("message", "")
    mode = getattr(backend, "mode", "extended")

    system_prompt = build_system_prompt(room=room, mode=mode)
    messages = build_messages_from_history(
        system_prompt=system_prompt,
        history=session_history,
        current_message=user_message,
    )

    loop.call_soon_threadsafe(q.put_nowait, {
        "type": "routing_info",
        "worker_id": f"cloud ({backend.get_provider_name()})",
        "model": backend.model_name,
        "provider": backend.get_provider_name(),
    })

    used_tools_dicts: list[dict] = []
    profiler_data: dict = {}
    t_start = time.time()

    def on_content_token(token: str) -> None:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": token})

    def on_tool_call(log_msg: str) -> None:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": log_msg})

    def on_raw_tool_call(tool_data: dict) -> None:
        used_tools_dicts.append(tool_data)

    def on_profiler(metric_data: dict) -> None:
        if metric_data and "metric" in metric_data:
            m = metric_data["metric"]
            val = metric_data.get("value", 0)
            profiler_data[m] = profiler_data.get(m, 0) + val
            loop.call_soon_threadsafe(q.put_nowait, {"type": "profiler", "content": metric_data})

    try:
        final_content = backend.generate_response(
            messages,
            app_state.tools_registry,
            on_content_token=on_content_token,
            on_tool_call=on_tool_call,
            on_raw_tool_call=on_raw_tool_call,
            on_profiler=on_profiler,
        )

        elapsed_ms = int((time.time() - t_start) * 1000.0)

        loop.call_soon_threadsafe(q.put_nowait, {
            "type": "done",
            "content": final_content,
            "elapsed_ms": elapsed_ms,
            "profiler": profiler_data,
        })

        turn = build_turn(
            user_message=user_message,
            assistant_response=final_content,
            satellite_id=satellite_id,
            room=room,
            worker_id=f"cloud ({backend.get_provider_name()})",
            model_name=backend.model_name,
            elapsed_ms=elapsed_ms,
            profiler=profiler_data,
            tools=used_tools_dicts,
            mode=mode,
        )
        await save_and_publish(satellite_id, turn)

    except Exception as e:
        logger.exception(f"Błąd w cloud pipeline: {e}")
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})
        raise
