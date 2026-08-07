"""
Pipeline worker — sekwencja STT → LLM (przez WebSocket do Klienta) → TTS.

Mechanizm _pending_tasks:
  Każde zadanie LLM wysłane do Klienta przez WebSocket dostaje unikalny task_id.
  Kontroler rejestruje task_id w _pending_tasks (słownik {task_id: asyncio.Queue}).
  Gdy Klient odsyła wyniki jako ramki task_event, api/clients.py wywołuje
  route_task_event() który wrzuca ramkę do właściwej kolejki.
  Pipeline czyta z kolejki aż do ramki {"type": "done"}, po czym czyści wpis.
  Eliminuje broken zależność od event_bus.subscribe(callback), które nie istnieje.
"""
import asyncio
import json
import logging
import time

import requests

import controller.core.app_state as app_state
import controller.core.client_store as client_store
from controller.core.connection_manager import client_manager
from controller.llm.prompt.builder import build_system_prompt
from controller.llm.prompt.tools_schema import get_tools_schema
from controller.llm.session.history import build_messages_from_history
from controller.llm.pipeline.session_manager import save_and_publish, build_turn

logger = logging.getLogger(__name__)

# Słownik aktywnych zadań LLM: {task_id: asyncio.Queue}
# Wpisy są tworzone przed wysłaniem komendy do Klienta i usuwane po odebraniu "done".
_pending_tasks: dict[str, asyncio.Queue] = {}


def route_task_event(task_id: str, event: dict) -> None:
    """
    Przekierowuje ramkę task_event z api/clients.py do kolejki oczekującego pipeline.

    Wywoływana z api/clients.py przy obsłudze msg_type == "task_event".
    Jest thread-safe — używa call_soon_threadsafe gdy pętla nie jest bieżąca.
    """
    q = _pending_tasks.get(task_id)
    if q is not None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"[Worker] Kolejka dla task_id={task_id} jest pełna — porzucam ramkę.")
    else:
        logger.debug(f"[Worker] Odebrano task_event dla nieznanego task_id={task_id} — ignoruję.")


async def run_worker_pipeline(
    payload: dict,
    llm_node: dict,
    session_history: list[dict],
    q: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    is_audio: bool = False,
    audio_bytes: bytes = None,
) -> None:
    """
    Wykonuje przebieg konwersacji przez węzeł lokalny: STT → LLM → TTS.

    Args:
        payload: Słownik żądania (room, satellite_id, message).
        llm_node: Metadane węzła LLM z client_store.get_llm_clients().
        session_history: Historia sesji do przekazania modelowi.
        q: Kolejka eventów SSE — tokeny i status są tu umieszczane.
        loop: Pętla zdarzeń asyncio.
        is_audio: True jeśli żądanie pochodzi z wejścia audio (wymaga STT i TTS).
        audio_bytes: Surowe bajty audio WAV (tylko gdy is_audio=True).
    """
    import uuid

    satellite_id = payload.get("satellite_id") or "web_ui"
    room = payload.get("room")
    node_id = llm_node["id"]
    mode = llm_node.get("mode", "extended")

    t_worker_start = time.time()
    final_content = ""
    stt_content = ""
    used_tools_dicts: list[dict] = []
    worker_profiler_data: dict = {}
    worker_elapsed_ms: int | None = None

    loop.call_soon_threadsafe(q.put_nowait, {
        "type": "routing_info",
        "worker_id": node_id,
        "model": llm_node.get("model_name", "nieznany"),
        "priority": llm_node.get("priority", 10),
    })

    try:
        # ─── KROK 1: TRANSKRYPCJA AUDIO (STT) ────────────────────────────────
        if is_audio:
            stt_nodes = client_store.get_audio_clients()
            if not stt_nodes:
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Brak dostępnej usługi STT."})
                return

            stt_node = stt_nodes[0]
            stt_url = f"{stt_node['base_url']}/v1/stt/transcribe"
            t_stt_start = time.time()

            try:
                files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
                stt_resp = await asyncio.to_thread(requests.post, stt_url, files=files, timeout=(1.0, 30.0))
                stt_resp.raise_for_status()
                stt_json = stt_resp.json()
                stt_content = stt_json.get("text", "")
                stt_ms = stt_json.get("elapsed_ms") or int((time.time() - t_stt_start) * 1000)
                worker_profiler_data["stt"] = stt_ms

                if not stt_content:
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Nie rozpoznano tekstu ze strumienia audio."})
                    return

                loop.call_soon_threadsafe(q.put_nowait, {"type": "stt_result", "content": stt_content})
            except Exception as e:
                logger.exception("Błąd usługi STT")
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": f"Błąd usługi STT: {e}"})
                return

        # ─── KROK 2: WNIOSKOWANIE LLM (przez WebSocket do Klienta) ──────────
        user_message = stt_content if is_audio else payload.get("message", "")
        system_prompt = build_system_prompt(room=room, mode=mode)

        if mode == "basic":
            tools_schema = get_tools_schema(names=["execute_action"])
        else:
            tools_schema = get_tools_schema()

        messages = build_messages_from_history(
            system_prompt=system_prompt,
            history=session_history,
            current_message=user_message,
        )

        max_iterations = 1 if mode == "basic" else 10

        for _ in range(max_iterations):
            task_id = str(uuid.uuid4())
            task_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
            _pending_tasks[task_id] = task_queue

            ws_payload = {"messages": messages, "tools": tools_schema}
            success = await client_manager.send_command(node_id, "chat_stream", {"task_id": task_id, **ws_payload})
            if not success:
                raise RuntimeError(f"Węzeł {node_id} nie odebrał komendy chat_stream.")

            tool_calls_to_execute = None

            try:
                while True:
                    ev = await asyncio.wait_for(task_queue.get(), timeout=120.0)
                    ev_type = ev.get("type")

                    if ev_type == "content":
                        loop.call_soon_threadsafe(q.put_nowait, ev)
                        final_content += ev.get("content", "")
                    elif ev_type == "profiler":
                        m = ev.get("content")
                        if isinstance(m, dict) and "metric" in m:
                            worker_profiler_data[m["metric"]] = worker_profiler_data.get(m["metric"], 0) + (m.get("value") or 0)
                            loop.call_soon_threadsafe(q.put_nowait, ev)
                    elif ev_type == "error":
                        raise RuntimeError(ev.get("content", "Błąd węzła"))
                    elif ev_type == "done":
                        worker_elapsed_ms = ev.get("elapsed_ms") or int((time.time() - t_worker_start) * 1000)
                        tool_calls_to_execute = ev.get("tool_calls")
                        break
            finally:
                _pending_tasks.pop(task_id, None)

            # Obsługa wywołań narzędzi (pętla ReAct)
            if tool_calls_to_execute:
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": tool_calls_to_execute,
                })

                for tc in tool_calls_to_execute:
                    function_name = tc["function"]["name"]
                    arguments = tc["function"]["arguments"]

                    if isinstance(arguments, str):
                        try:
                            args_dict = json.loads(arguments)
                        except json.JSONDecodeError:
                            args_dict = {}
                    else:
                        args_dict = arguments

                    used_tools_dicts.append({"name": function_name, "arguments": args_dict})
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "type": "tool_dict",
                        "content": {"name": function_name, "arguments": args_dict},
                    })
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "type": "tool_call_raw",
                        "content": f"Używam narzędzia: {function_name} z argumentami: {json.dumps(args_dict, ensure_ascii=False)}",
                    })

                    t_tool = time.time()
                    result = await asyncio.to_thread(app_state.tools_registry.execute_tool, function_name, args_dict)
                    tool_time_ms = (time.time() - t_tool) * 1000.0
                    worker_profiler_data["tool_exec"] = worker_profiler_data.get("tool_exec", 0) + tool_time_ms
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "type": "profiler",
                        "content": {"metric": "tool_exec", "value": tool_time_ms},
                    })

                    messages.append({
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps(result, ensure_ascii=False),
                    })
                # Kontynuuj pętlę ReAct
                continue
            else:
                break

        # ─── KROK 3: SYNTEZA MOWY (TTS) ──────────────────────────────────────
        if is_audio and final_content:
            tts_nodes = client_store.get_audio_clients()
            if tts_nodes:
                tts_node = tts_nodes[0]
                tts_url = f"{tts_node['base_url']}/v1/tts/synthesize"
                try:
                    t_tts_start = time.time()
                    tts_resp = await asyncio.to_thread(
                        requests.post, tts_url,
                        json={"text": final_content},
                        timeout=(1.0, 30.0),
                    )
                    if tts_resp.ok:
                        tts_json = tts_resp.json()
                        b64_audio = tts_json.get("audio_b64")
                        tts_ms = tts_json.get("elapsed_ms") or int((time.time() - t_tts_start) * 1000)
                        worker_profiler_data["tts"] = tts_ms
                        if b64_audio:
                            loop.call_soon_threadsafe(q.put_nowait, {"type": "tts_audio", "content": b64_audio})
                except Exception as e:
                    logger.warning(f"Błąd usługi TTS: {e}")

        # ─── FINALIZACJA ──────────────────────────────────────────────────────
        if not worker_elapsed_ms:
            worker_elapsed_ms = int((time.time() - t_worker_start) * 1000.0)

        loop.call_soon_threadsafe(q.put_nowait, {
            "type": "done",
            "content": final_content,
            "elapsed_ms": worker_elapsed_ms,
            "profiler": worker_profiler_data,
        })

        if final_content and user_message:
            turn = build_turn(
                user_message=user_message,
                assistant_response=final_content,
                satellite_id=satellite_id,
                room=room,
                worker_id=node_id,
                model_name=llm_node.get("model_name", "nieznany"),
                elapsed_ms=worker_elapsed_ms,
                profiler=worker_profiler_data,
                tools=used_tools_dicts,
                mode=mode,
            )
            await save_and_publish(satellite_id, turn)

    except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
        logger.warning(f"Węzeł {node_id} nie odpowiada — usuwam z rejestru. ({e})")
        client_store.client_registry.pop(node_id, None)
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Węzeł zawiódł."})
    except Exception as e:
        logger.exception(f"Błąd worker pipeline dla węzła {node_id}")
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})
