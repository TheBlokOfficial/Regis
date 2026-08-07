import json
import logging
import asyncio
from datetime import datetime

from protocol.schemas import WSClientEvent

from client.config import (
    _get_settings, reload_settings, _get_client_id,
    get_controller_url, reset_discovered_controller_url
)
from client.network.client_registry import (
    register, unregister, apply_service_config
)
from client.network.ws_transport import (
    start_ws_client, wait_for_ws_connection, get_ws_client, get_ws_loop, set_message_handler
)
from client.network.ws_dispatcher import (
    handle_ws_message, set_wake_check_callback
)

logger = logging.getLogger(__name__)

# Rejestracja dispatchera w transporcie
set_message_handler(handle_ws_message)

def _get_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

def bus_publish(event: dict) -> None:
    """Wysyła zdarzenie bezpośrednio przez otwarty WebSocket do Kontrolera."""
    if "timestamp" not in event:
        event["timestamp"] = _get_timestamp()
    
    ws_loop = get_ws_loop()
    ws_client = get_ws_client()
    
    if ws_loop and ws_client:
        ws_event = WSClientEvent(
            event_type=event.get("type", "unknown"),
            data=event
        )
        asyncio.run_coroutine_threadsafe(ws_client.send(ws_event.model_dump_json()), ws_loop)


def send_audio_complete() -> None:
    """
    Informuje Kontroler przez WebSocket, że Satelita zakończyła odtwarzanie audio.
    """
    ws_loop = get_ws_loop()
    ws_client = get_ws_client()
    if ws_loop and ws_client:
        msg = json.dumps({"type": "audio_complete"})
        asyncio.run_coroutine_threadsafe(ws_client.send(msg), ws_loop)


async def request_wake_permission(timeout: float = 2.0) -> bool:
    """Wysyła zapytanie do Kontrolera o pozwolenie na nagrywanie i czeka na odpowiedź."""
    ws_loop = get_ws_loop()
    ws_client = get_ws_client()
    if not ws_loop or not ws_client:
        return False
        
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    
    def resolve(permitted: bool):
        if not future.done():
            loop.call_soon_threadsafe(future.set_result, permitted)
            
    set_wake_check_callback(resolve)
    
    try:
        req = {"type": "wake_check"}
        asyncio.run_coroutine_threadsafe(ws_client.send(json.dumps(req)), ws_loop)
        
        result = await asyncio.wait_for(future, timeout)
        return result
    except asyncio.TimeoutError:
        logger.warning("Timeout podczas oczekiwania na wake_check_result.")
        return False
    except Exception as e:
        logger.error(f"Błąd podczas request_wake_permission: {e}")
        return False
    finally:
        set_wake_check_callback(None)


def send_task_result(task_id: str, event: dict) -> None:
    """Przesyła zdarzenie/ramkę wyniku z usługi podrzędnej przez WebSocket do Kontrolera."""
    ws_loop = get_ws_loop()
    ws_client = get_ws_client()
    if ws_client and ws_loop and ws_loop.is_running():
        payload = json.dumps({"type": "task_event", "task_id": task_id, "event": event})
        asyncio.run_coroutine_threadsafe(ws_client.send(payload), ws_loop)
