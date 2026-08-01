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
from controller.openrouter_backend import OpenRouterBackend

logger = logging.getLogger(__name__)


def proxy_sse_to_queue(
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

    if not is_audio and isinstance(backend, OpenRouterBackend):
        # Phase 1: OpenRouter (chmura) wywoływany bezpośrednio na Kontrolerze (tylko tekst)
        system_prompt = build_system_prompt(room=room, native_tools=True)

        from core.history_utils import build_messages_from_history
        messages = build_messages_from_history(
            system_prompt=system_prompt,
            history=session_history,
            current_message=base_payload.get("message", "")
        )

        logging.info("Routowanie żądania bezpośrednio do: OpenRouter")

        routing_event = {
            "type": "routing_info",
            "worker_id": "cloud (OpenRouter)",
            "model": backend.model_name,
            "provider": backend.get_provider_name(),
        }
        loop.call_soon_threadsafe(q.put_nowait, routing_event)

        used_tools_dicts = []

        def on_content_token(token):
            loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": token})

        def on_tool_call(log_msg):
            loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": log_msg})

        def on_raw_tool_call(tool_data):
            used_tools_dicts.append(tool_data)

        try:
            final_content = backend.generate_response(
                messages,
                registry.tools_registry,
                on_content_token=on_content_token,
                on_tool_call=on_tool_call,
                on_raw_tool_call=on_raw_tool_call
            )

            loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": final_content})

            now = datetime.datetime.now().strftime("%H:%M:%S")
            turn = {
                "user": base_payload.get("message", ""),
                "assistant": final_content,
                "tools": used_tools_dicts,
                "timestamp": now,
                "satellite_id": satellite_id,
                "room": room
            }
            registry.append_to_session(satellite_id, turn)

            # Publikuj zdarzenie do Web UI EventBus
            asyncio.run_coroutine_threadsafe(
                event_bus.publish({
                    "type": "conversation_turn",
                    "user_text": base_payload.get("message", ""),
                    "assistant_text": final_content,
                    "worker_id": "cloud (OpenRouter)",
                    "satellite_id": satellite_id,
                    "room": room,
                    "tool_count": len(used_tools_dicts),
                }),
                loop
            )

            from core import config
            limit = config.load_settings().get("history_limit", 3)
            hist = registry.get_session_history(satellite_id)
            if limit <= 0:
                registry.clear_session_history(satellite_id)
            elif len(hist) > limit:
                del hist[:-limit]

            return  # Zakończ sukcesem

        except Exception as e:
            logging.warning(f"Błąd w OpenRouterBackend, próba fallbacku na węzeł: {e}")
            force_worker = True

    if is_audio or not isinstance(backend, OpenRouterBackend) or force_worker:
        workers = registry.get_worker_nodes()
        if not workers:
            loop.call_soon_threadsafe(
                q.put_nowait,
                {"type": "error", "content": "Brak dostępnego providera LLM (wymagany worker dla zapytania audio/lokalnego)."}
            )
            return

        # Priorytetyzacja: sortowanie malejąco po priority (100 wyżej niż 10)
        sorted_workers = sorted(workers, key=lambda w: w.get("priority", 10), reverse=True)
        worker = sorted_workers[0]
        worker_id = worker["id"]
        prio = worker.get("priority", 10)

        system_prompt = build_system_prompt(room=room)

        if not is_audio:
            worker_url = f"{worker['base_url']}/v1/chat/stream"
            payload = dict(base_payload)
            payload["system_prompt"] = system_prompt
            payload["history"] = session_history
        else:
            worker_url = f"{worker['base_url']}/v1/chat/audio_stream"

        logging.info(f"Routowanie żądania do węzła: {worker_id} (priority={prio})")
        logger.debug(
            f"Router wybrany węzeł: id={worker_id} | priority={prio} "
            f"| model={worker.get('model_name', 'nieznany')} | url={worker_url}"
        )

        routing_event = {
            "type": "routing_info",
            "worker_id": worker_id,
            "model": worker.get("model_name", "nieznany"),
            "priority": prio,
        }
        loop.call_soon_threadsafe(q.put_nowait, routing_event)

        final_content = ""
        stt_content = ""
        used_tools_dicts = []

        try:
            if not is_audio:
                resp = requests.post(worker_url, json=payload, stream=True, timeout=(1.0, 300.0))
            else:
                files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
                data = dict(base_payload)
                data["system_prompt"] = system_prompt
                data["history"] = json.dumps(session_history)
                resp = requests.post(worker_url, files=files, data=data, stream=True, timeout=(1.0, 300.0))

            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        if event.get("type") == "stt_result":
                            stt_content = event.get("content", "")
                        elif event.get("type") == "tool_dict":
                            used_tools_dicts.append(event.get("content"))
                        elif event.get("type") == "done":
                            final_content = event.get("content", "")

                        loop.call_soon_threadsafe(q.put_nowait, event)
                        if event.get("type") in ("done", "error"):
                            break
                    except json.JSONDecodeError:
                        pass

            if final_content:
                user_msg = stt_content if is_audio else base_payload.get("message", "")
                if user_msg and final_content != "Przerwano zapytanie. Przekroczono maksymalną liczbę wywołań narzędzi (timeout pętli ReAct).":
                    now = datetime.datetime.now().strftime("%H:%M:%S")
                    turn = {
                        "user": user_msg,
                        "assistant": final_content,
                        "tools": used_tools_dicts,
                        "timestamp": now,
                        "satellite_id": satellite_id,
                        "room": room
                    }
                    registry.append_to_session(satellite_id, turn)

                    # Publikuj zdarzenie do Web UI EventBus
                    asyncio.run_coroutine_threadsafe(
                        event_bus.publish({
                            "type": "conversation_turn",
                            "user_text": user_msg,
                            "assistant_text": final_content,
                            "worker_id": worker_id,
                            "satellite_id": satellite_id,
                            "room": room,
                            "tool_count": len(used_tools_dicts),
                        }),
                        loop
                    )

                    from core import config
                    limit = config.load_settings().get("history_limit", 3)
                    hist = registry.get_session_history(satellite_id)
                    if limit <= 0:
                        registry.clear_session_history(satellite_id)
                    elif len(hist) > limit:
                        del hist[:-limit]

        except (requests.exceptions.ConnectTimeout, requests.exceptions.ConnectionError) as e:
            logging.warning(f"Węzeł {worker_id} nie odpowiada (Connect błąd). Usuwam z rejestru.")
            logger.debug(f"Router timeout/conn error | worker_id={worker_id} | url={worker_url} | błąd: {e}")
            if worker_id in registry.worker_registry:
                del registry.worker_registry[worker_id]
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Węzeł zawiódł."})
        except Exception as e:
            logging.exception(f"Inny błąd proxy do węzła {worker_id}")
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})


def clear_conversation_history(satellite_id: str | None = None):
    """Resetuje historię konwersacji w pamięci Kontrolera oraz powiązanych Węzłach."""
    registry.clear_session_history(satellite_id)

    for worker in registry.get_worker_nodes():
        try:
            requests.post(f"{worker['base_url']}/v1/clear_history", timeout=2)
        except Exception:
            pass
