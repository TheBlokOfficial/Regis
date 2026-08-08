"""
Silnik Agenta ReAct (Warstwa 1 — Core / Agent Engine).

Jedno miejsce orkiestracji wieloturowej konwersacji agenta ReAct.
Obsługuje:
- Pętlę iteracji ReAct (max_iterations)
- Strumieniowanie odpowiedzi i zdarzeń do kolejki SSE (q)
- Wywoływanie narzędzi w rejestrze (tools_registry)
- Mierzenie statystyk wykonania (profiler)
- Zapis ukończonej tury konwersacji do historii sesji
"""
import asyncio
import json
import logging
import time
from typing import Any

import controller.core.app_state as app_state
from controller.agent.prompt.builder import build_system_prompt
from controller.agent.prompt.tools_schema import get_tools_schema
from controller.core.session.history import build_messages_from_history
from controller.core.session.manager import save_and_publish, build_turn

logger = logging.getLogger(__name__)


class _SSEEmitter:
    """Klasa pomocnicza ukrywająca szczegóły przekazywania zdarzeń do kolejki asyncio."""
    
    def __init__(self, q: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        self.q = q
        self.loop = loop
        self.profiler_data: dict = {}

    def emit_content(self, event: dict):
        self.loop.call_soon_threadsafe(self.q.put_nowait, event)

    def emit_tool_call_raw(self, function_name: str, args_str: str):
        log_text = f"> Regis używa: {function_name}({args_str})"
        self.loop.call_soon_threadsafe(self.q.put_nowait, {"type": "tool_call_raw", "content": log_text})

    def emit_profiler_metric(self, metric: str, value: float):
        self.profiler_data[metric] = self.profiler_data.get(metric, 0) + value
        self.loop.call_soon_threadsafe(self.q.put_nowait, {
            "type": "profiler", 
            "content": {"metric": metric, "value": value}
        })

    def emit_done(self, final_content: str, elapsed_ms: int):
        self.loop.call_soon_threadsafe(self.q.put_nowait, {
            "type": "done",
            "content": final_content,
            "elapsed_ms": elapsed_ms,
            "profiler": self.profiler_data,
        })
        
    def process_stream_event(self, ev: dict):
        """Pomocnicze przekierowanie zdarzeń ze strumienia do kolejki SSE i profilerów."""
        ev_type = ev.get("type")
        if ev_type == "content":
            self.emit_content(ev)
        elif ev_type == "profiler":
            m = ev.get("metric") or (ev.get("content", {}).get("metric") if isinstance(ev.get("content"), dict) else None)
            val = ev.get("value") or (ev.get("content", {}).get("value") if isinstance(ev.get("content"), dict) else 0)
            if m:
                self.emit_profiler_metric(m, val)


async def _consume_stream(stream_res: Any, emitter: _SSEEmitter) -> tuple[str, list[dict]]:
    """Pobiera i scala strumień od modelu, używając SSEEmitter do propagacji na żywo."""
    current_content = ""
    current_tool_calls: list[dict] = []

    if hasattr(stream_res, "__aiter__"):
        async for event in stream_res:
            emitter.process_stream_event(event)
            if event.get("type") == "content":
                current_content += event.get("content", "")
            elif event.get("type") == "tool_calls":
                current_tool_calls = event.get("tool_calls", [])
    else:
        for event in stream_res:
            emitter.process_stream_event(event)
            if event.get("type") == "content":
                current_content += event.get("content", "")
            elif event.get("type") == "tool_calls":
                current_tool_calls = event.get("tool_calls", [])

    return current_content, current_tool_calls


def _execute_tool_calls(
    tool_calls: list[dict], 
    tools_registry: Any, 
    emitter: _SSEEmitter, 
    used_tools_dicts: list[dict]
) -> list[dict]:
    """Wykonuje listę zaplanowanych narzędzi i zwraca ich zserializowane wyniki dla historii."""
    tool_messages = []

    for tc in tool_calls:
        function_name = tc.get("function", {}).get("name", "")
        arguments_raw = tc.get("function", {}).get("arguments", {})

        if isinstance(arguments_raw, str):
            try:
                args_dict = json.loads(arguments_raw)
            except json.JSONDecodeError:
                args_dict = {}
        else:
            args_dict = arguments_raw or {}

        args_str = ", ".join(f"{k}={v}" for k, v in args_dict.items())
        emitter.emit_tool_call_raw(function_name, args_str)

        t_tool_start = time.time()
        if tools_registry:
            tool_result = tools_registry.execute_tool(function_name, args_dict)
        else:
            tool_result = "Błąd: Brak dostępu do narzędzi."
        t_tool_dur = (time.time() - t_tool_start) * 1000.0

        emitter.emit_profiler_metric("tools", t_tool_dur)

        used_tools_dicts.append({
            "name": function_name,
            "arguments": args_dict,
            "result": tool_result
        })

        tool_msg = {
            "role": "tool",
            "name": function_name,
            "tool_call_id": tc.get("id", f"call_{function_name}"),
            "content": json.dumps(tool_result, ensure_ascii=False) if not isinstance(tool_result, str) else tool_result
        }
        tool_messages.append(tool_msg)

    return tool_messages


async def run_agent_loop(
    stream_provider: Any,
    session_history: list[dict],
    user_message: str,
    satellite_id: str,
    room: str | None,
    worker_id: str,
    model_name: str,
    q: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    tools_registry: Any = None,
) -> str:
    """
    Uruchamia pętlę ReAct dla przekazanego dostawcy strumienia.
    """
    if tools_registry is None:
        tools_registry = app_state.tools_registry

    system_prompt = build_system_prompt(room=room)
    messages = build_messages_from_history(
        system_prompt=system_prompt,
        history=session_history,
        current_message=user_message,
    )

    max_iterations = 10
    iteration_count = 0

    used_tools_dicts: list[dict] = []
    emitter = _SSEEmitter(q, loop)
    t_start = time.time()
    final_content = ""

    while iteration_count < max_iterations:
        iteration_count += 1

        tools_schema = get_tools_schema()

        try:
            if hasattr(stream_provider, "chat_stream"):
                stream_res = stream_provider.chat_stream(messages, tools=tools_schema)
            elif callable(stream_provider):
                stream_res = stream_provider(messages, tools=tools_schema)
            else:
                raise ValueError("stream_provider musi posiadać metodę chat_stream lub być callable")

            current_content, current_tool_calls = await _consume_stream(stream_res, emitter)

            if current_content:
                final_content = current_content

            if current_tool_calls:
                # Agent zdecydował się użyć narzędzi - zapiszemy co pomyślał, wywołamy je i będziemy kontynuować pętlę.
                assistant_msg = {"role": "assistant", "content": current_content, "tool_calls": current_tool_calls}
                messages.append(assistant_msg)

                tool_messages = _execute_tool_calls(current_tool_calls, tools_registry, emitter, used_tools_dicts)
                messages.extend(tool_messages)
            else:
                # Agent zwrócił sam tekst bez chęci używania narzędzi - koniec tury.
                break

        except Exception as e:
            logger.exception(f"Błąd w pętli ReAct agenta: {e}")
            raise

    elapsed_ms = int((time.time() - t_start) * 1000.0)
    emitter.emit_done(final_content, elapsed_ms)

    if user_message and final_content:
        turn = build_turn(
            user_message=user_message,
            assistant_response=final_content,
            satellite_id=satellite_id,
            room=room,
            worker_id=worker_id,
            model_name=model_name,
            elapsed_ms=elapsed_ms,
            profiler=emitter.profiler_data,
            tools=used_tools_dicts,
        )
        await save_and_publish(satellite_id, turn)

    return final_content
