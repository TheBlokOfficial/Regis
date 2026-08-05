import asyncio
import datetime
import json
import logging
import time

import requests

import controller.event_bus as event_bus

import controller.providers as providers
import controller.registry as registry
from controller.services.prompt_builder import build_system_prompt
from controller.llm_backends.ollama import OllamaBackend

logger = logging.getLogger(__name__)


async def proxy_sse_to_queue(
    base_payload: dict,
    q: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    is_audio: bool = False,
    audio_bytes: bytes = None
):
    """Odczytuje SSE z Workerów lub odpytuje chmurę bezpośrednio i umieszcza eventy w asyncio.Queue."""
    registry.last_interaction_time = time.time()

    backend = providers.get_llm_backend()
    if backend is None:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Brak dostępnego providera LLM."})
        return

    room = base_payload.get("room")
    satellite_id = base_payload.get("satellite_id") or "web_ui"
    session_history = registry.get_session_history(satellite_id)
    force_worker = False

    if not is_audio and not isinstance(backend, OllamaBackend):
        # Phase 1: Chmura wywoływana bezpośrednio na Kontrolerze (tylko tekst)
        mode = getattr(backend, "mode", "extended")
        system_prompt = build_system_prompt(room=room, mode=mode)

        from controller.history_utils import build_messages_from_history
        messages = build_messages_from_history(
            system_prompt=system_prompt,
            history=session_history,
            current_message=base_payload.get("message", "")
        )

        logging.info("Routowanie żądania bezpośrednio do: OpenRouter")

        routing_event = {
            "type": "routing_info",
            "worker_id": f"cloud ({backend.get_provider_name()})",
            "model": backend.model_name,
            "provider": backend.get_provider_name(),
        }
        loop.call_soon_threadsafe(q.put_nowait, routing_event)

        used_tools_dicts = []
        profiler_data = {}
        t_start = time.time()

        def on_content_token(token):
            loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": token})

        def on_tool_call(log_msg):
            loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": log_msg})

        def on_raw_tool_call(tool_data):
            used_tools_dicts.append(tool_data)

        def on_profiler(metric_data):
            if metric_data and "metric" in metric_data:
                m = metric_data["metric"]
                val = metric_data.get("value", 0)
                profiler_data[m] = profiler_data.get(m, 0) + val
                loop.call_soon_threadsafe(q.put_nowait, {"type": "profiler", "content": metric_data})

        try:
            final_content = backend.generate_response(
                messages,
                registry.tools_registry,
                on_content_token=on_content_token,
                on_tool_call=on_tool_call,
                on_raw_tool_call=on_raw_tool_call,
                on_profiler=on_profiler
            )

            elapsed_ms = int((time.time() - t_start) * 1000.0)

            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "done",
                "content": final_content,
                "elapsed_ms": elapsed_ms,
                "profiler": profiler_data
            })

            now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
            turn = {
                "user": base_payload.get("message", ""),
                "assistant": final_content,
                "tools": used_tools_dicts,
                "timestamp": now,
                "satellite_id": satellite_id,
                "room": room,
                "elapsed_ms": elapsed_ms,
                "profiler": profiler_data,
                "model": backend.model_name
            }
            registry.append_to_session(satellite_id, turn)

            # Publikuj zdarzenie do Web UI EventBus
            await event_bus.publish({
                    "type": "conversation_turn",
                    "user_text": base_payload.get("message", ""),
                    "assistant_text": final_content,
                    "worker_id": f"cloud ({backend.get_provider_name()})",
                    "satellite_id": satellite_id,
                    "room": room,
                    "tools": used_tools_dicts,
                    "tool_count": len(used_tools_dicts),
                    "elapsed_ms": elapsed_ms,
                    "profiler": profiler_data,
                    "model": backend.model_name
                })

            if mode != "basic":
                from controller import config
                limit = config.load_settings().get("history_limit", 3)
                hist = registry.get_session_history(satellite_id)
                if limit <= 0:
                    registry.clear_session_history(satellite_id)
                elif len(hist) > limit:
                    del hist[:-limit]
            else:
                # Basic mode jest bezstanowy
                registry.clear_session_history(satellite_id)

            return  # Zakończ sukcesem

        except Exception as e:
            logging.warning(f"Błąd w OpenRouterBackend, próba fallbacku na węzeł: {e}")
            force_worker = True

    if is_audio or isinstance(backend, OllamaBackend) or force_worker:
        t_worker_start = time.time()
        final_content = ""
        stt_content = ""
        used_tools_dicts = []
        worker_profiler_data = {}
        worker_elapsed_ms = None

        # ─── KROK 1: TRANSKRYPCJA AUDIO (STT) ───────────────────────────────
        if is_audio:
            stt_nodes = registry.get_stt_nodes()
            if not stt_nodes:
                loop.call_soon_threadsafe(
                    q.put_nowait,
                    {"type": "error", "content": "Brak dostępnej usługi STT (Whisper)."}
                )
                return
            stt_node = stt_nodes[0]
            stt_url = f"{stt_node['base_url']}/v1/stt/transcribe"

            t_stt_start = time.time()
            try:
                files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
                import asyncio
                stt_resp = await asyncio.to_thread(requests.post, stt_url, files=files, timeout=(1.0, 30.0))
                stt_resp.raise_for_status()
                stt_json = stt_resp.json()
                stt_content = stt_json.get("text", "")
                stt_ms = stt_json.get("elapsed_ms") or int((time.time() - t_stt_start) * 1000)
                worker_profiler_data["stt"] = stt_ms

                if not stt_content:
                    loop.call_soon_threadsafe(
                        q.put_nowait,
                        {"type": "error", "content": "Nie rozpoznano żadnego tekstu ze strumienia audio."}
                    )
                    return

                loop.call_soon_threadsafe(q.put_nowait, {"type": "stt_result", "content": stt_content})
            except Exception as e:
                logging.exception("Błąd usługi STT")
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": f"Błąd usugi STT: {e}"})
                return

        # ─── KROK 2: WNIOSKOWANIE I GENERACJA (LLM) ──────────────────────────
        llm_nodes = registry.get_llm_nodes()
        if not llm_nodes:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "error", "content": "Brak dostępnej usługi LLM."}
            )
            return

        sorted_llm_nodes = sorted(llm_nodes, key=lambda w: w.get("priority", 10), reverse=True)
        llm_node = sorted_llm_nodes[0]
        node_id = llm_node["id"]
        prio = llm_node.get("priority", 10)

        mode = llm_node.get("mode", "extended")
        system_prompt = build_system_prompt(room=room, mode=mode)

        from controller.schemas_tools import get_tools_schema
        if mode == "basic":
            tools_schema = get_tools_schema(names=["execute_action"])
        else:
            tools_schema = get_tools_schema()

        llm_url = f"{llm_node['base_url']}/v1/chat/stream"
        user_message = stt_content if is_audio else base_payload.get("message", "")

        payload = {
            "message": user_message,
            "system_prompt": system_prompt,
            "history": session_history,
            "tools": tools_schema,
            "controller_url": base_payload.get("controller_url"),
            "room": room,
        }

        routing_event = {
            "type": "routing_info",
            "worker_id": node_id,
            "model": llm_node.get("model_name", "nieznany"),
            "priority": prio,
        }
        loop.call_soon_threadsafe(q.put_nowait, routing_event)

        try:
            import uuid
            
            # Pętla ReAct (obsługa Tool Calling z Węzła)
            max_iterations = 10 if mode != "basic" else 1
            iteration_count = 0
            
            while iteration_count < max_iterations:
                iteration_count += 1
                
                my_task_id = str(uuid.uuid4())
                
                # Zastąpienie history/system_prompt pełną listą messages
                from controller.history_utils import build_messages_from_history
                if iteration_count == 1:
                    messages = build_messages_from_history(
                        system_prompt=system_prompt,
                        history=session_history,
                        current_message=user_message
                    )
                else:
                    # Wiadomości są budowane/aktualizowane w samej pętli
                    pass 
                
                # Przesyłamy messages bezpośrednio
                ws_payload = {
                    "messages": messages,
                    "tools": tools_schema,
                }
                
                # Uruchamiamy kolejkę tymczasową dla eventów z Węzła
                event_queue = asyncio.Queue()
                
                async def event_handler(event_data):
                    if event_data.get("task_id") == my_task_id:
                        await event_queue.put(event_data.get("event", {}))
                
                # Subskrypcja (używamy event_bus.subscribe(callback))
                sub_id = event_bus.subscribe(event_handler, event_types=["task_event"])
                
                # Wysyłamy komendę chat_stream
                success = await registry.node_manager.send_command(node_id, "chat_stream", {"task_id": my_task_id, **ws_payload})
                if not success:
                    raise Exception(f"Węzeł {node_id} nie odebrał komendy chat_stream")
                
                tool_calls_to_execute = None
                
                try:
                    while True:
                        ev = await asyncio.wait_for(event_queue.get(), timeout=120.0)
                        ev_type = ev.get("type")
                        if ev_type == "content":
                            loop.call_soon_threadsafe(q.put_nowait, ev)
                            final_content += ev.get("content", "")
                        elif ev_type == "profiler":
                            m = ev.get("content")
                            if m and isinstance(m, dict) and "metric" in m:
                                worker_profiler_data[m["metric"]] = worker_profiler_data.get(m["metric"], 0) + (m.get("value") or 0)
                                loop.call_soon_threadsafe(q.put_nowait, ev)
                        elif ev_type == "error":
                            raise Exception(ev.get("content", "Błąd węzła"))
                        elif ev_type == "done":
                            worker_elapsed_ms = ev.get("elapsed_ms") or int((time.time() - t_worker_start) * 1000.0)
                            tc = ev.get("tool_calls")
                            if tc:
                                tool_calls_to_execute = tc
                            break
                finally:
                    event_bus.unsubscribe(sub_id)
                
                # Po odebraniu 'done', sprawdzamy czy są narzędzia do wykonania
                if tool_calls_to_execute:
                    # Dodaj odpowiedź asystenta do messages
                    messages.append({
                        "role": "assistant",
                        "content": "",
                        "tool_calls": tool_calls_to_execute
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
                            
                        # Informuj UI o rozpoczęciu narzędzia
                        used_tools_dicts.append({"name": function_name, "arguments": args_dict})
                        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_dict", "content": {"name": function_name, "arguments": args_dict}})
                        loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": f"Używam narzędzia: {function_name} z argumentami: {json.dumps(args_dict, ensure_ascii=False)}"})
                        
                        t_tool = time.time()
                        # Wykonujemy lokalnie w Kontrolerze!
                        result = await asyncio.to_thread(registry.tools_registry.execute_tool, function_name, args_dict)
                        tool_time_ms = (time.time() - t_tool) * 1000.0
                        
                        worker_profiler_data["tool_exec"] = worker_profiler_data.get("tool_exec", 0) + tool_time_ms
                        loop.call_soon_threadsafe(q.put_nowait, {"type": "profiler", "content": {"metric": "tool_exec", "value": tool_time_ms}})
                        
                        messages.append({
                            "role": "tool",
                            "name": function_name,
                            "content": json.dumps(result, ensure_ascii=False)
                        })
                    
                    # Kontynuuj pętlę ReAct (wyślij messages z nowymi odpowiedziami z narzędzi do LLM)
                    continue
                else:
                    # Koniec iteracji, brak narzędzi do wykonania
                    break

            # ─── KROK 3: SYNTEZA MOWY (TTS) ──────────────────────────────────
            if is_audio and final_content:
                tts_nodes = registry.get_tts_nodes()
                if tts_nodes:
                    tts_node = tts_nodes[0]
                    tts_url = f"{tts_node['base_url']}/v1/tts/synthesize"
                    try:
                        t_tts_start = time.time()
                        tts_resp = await asyncio.to_thread(requests.post, tts_url, json={"text": final_content}, timeout=(1.0, 30.0))
                        if tts_resp.ok:
                            tts_json = tts_resp.json()
                            b64_audio = tts_json.get("audio_b64")
                            tts_ms = tts_json.get("elapsed_ms") or int((time.time() - t_tts_start) * 1000)
                            worker_profiler_data["tts"] = tts_ms
                            if b64_audio:
                                loop.call_soon_threadsafe(q.put_nowait, {"type": "tts_audio", "content": b64_audio})
                    except Exception as e:
                        logging.warning(f"Błąd usługi TTS: {e}")

            if not worker_elapsed_ms:
                worker_elapsed_ms = int((time.time() - t_worker_start) * 1000.0)

            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "done",
                "content": final_content,
                "elapsed_ms": worker_elapsed_ms,
                "profiler": worker_profiler_data
            })

            if final_content:
                user_msg = stt_content if is_audio else base_payload.get("message", "")
                if user_msg:
                    now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
                    turn = {
                        "user": user_msg,
                        "assistant": final_content,
                        "tools": used_tools_dicts,
                        "timestamp": now,
                        "satellite_id": satellite_id,
                        "room": room,
                        "elapsed_ms": worker_elapsed_ms,
                        "profiler": worker_profiler_data,
                        "model": llm_node.get("model_name", "nieznany")
                    }
                    registry.append_to_session(satellite_id, turn)

                    # Publikuj zdarzenie do Web UI EventBus
                    await event_bus.publish({
                            "type": "conversation_turn",
                            "user_text": user_msg,
                            "assistant_text": final_content,
                            "worker_id": node_id,
                            "satellite_id": satellite_id,
                            "room": room,
                            "tools": used_tools_dicts,
                            "tool_count": len(used_tools_dicts),
                            "elapsed_ms": worker_elapsed_ms,
                            "profiler": worker_profiler_data,
                            "model": llm_node.get("model_name", "nieznany")
                        })

                    if mode != "basic":
                        from controller import config
                        limit = config.load_settings().get("history_limit", 3)
                        hist = registry.get_session_history(satellite_id)
                        if limit <= 0:
                            registry.clear_session_history(satellite_id)
                        elif len(hist) > limit:
                            del hist[:-limit]
                    else:
                        registry.clear_session_history(satellite_id)

        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
            logging.warning(f"Węzeł {node_id} nie odpowiada (Connect błąd). Usuwam z rejestru.")
            logger.debug(f"Router timeout/conn error | worker_id={node_id} | błąd: {e}")
            if node_id in registry.node_registry:
                del registry.node_registry[node_id]
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Węzeł zawiódł."})
        except Exception as e:
            logging.exception(f"Inny błąd proxy do węzła {node_id}")
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})


def clear_conversation_history(satellite_id: str | None = None):
    """Resetuje historię konwersacji w pamięci Kontrolera oraz powiązanych Węzłach."""
    registry.clear_session_history(satellite_id)

    for worker in registry.get_worker_nodes():
        try:
            requests.post(f"{worker['base_url']}/v1/clear_history", timeout=2)
        except Exception:
            pass
