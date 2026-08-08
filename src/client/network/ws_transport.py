import logging
import asyncio
import threading
import websockets
from typing import Any, Callable, Awaitable

from client.config import _get_client_id, get_controller_url, reset_discovered_controller_url

logger = logging.getLogger(__name__)

_ws_loop: asyncio.AbstractEventLoop | None = None
_ws_client: Any = None
_ws_connected_event = threading.Event()
_message_handler: Callable[[Any, str], Awaitable[None]] | None = None


def set_message_handler(handler: Callable[[Any, str], Awaitable[None]]) -> None:
    """Rejestruje handler przychodzących wiadomości z WebSocket."""
    global _message_handler
    _message_handler = handler


def get_ws_loop() -> asyncio.AbstractEventLoop | None:
    return _ws_loop


def get_ws_client() -> Any:
    return _ws_client


def wait_for_ws_connection(timeout: float = 3.0) -> bool:
    """Oczekuje synchronicznie na nawiązanie połączenia WebSocket z Kontrolerem."""
    return _ws_connected_event.wait(timeout=timeout)


async def _heartbeat_ping_loop(ws: Any) -> None:
    """Wysyła ramkę keep-alive co 20 sekund, aby odświeżać last_seen w Kontrolerze."""
    import json
    try:
        while True:
            await asyncio.sleep(20.0)
            await ws.send(json.dumps({"type": "status"}))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.debug(f"Pętla heartbeat WS przerwana: {e}")


async def _ws_client_loop() -> None:
    global _ws_client
    
    client_id = _get_client_id()
    
    while True:
        try:
            controller_url = get_controller_url(allow_fallback=False)
            ws_url = controller_url.replace("http://", "ws://").replace("https://", "wss://") + f"/v1/ws/clients/{client_id}"
            
            async with websockets.connect(ws_url) as ws:
                _ws_client = ws
                logger.info(f"Połączono z Kontrolerem przez WebSocket ({ws_url}).")
                _ws_connected_event.set()
                
                from client.network.client_registry import register
                register()
                
                ping_task = asyncio.create_task(_heartbeat_ping_loop(ws))
                try:
                    async for message in ws:
                        try:
                            if _message_handler:
                                await _message_handler(ws, message)
                        except Exception as e:
                            logger.error(f"Błąd przetwarzania komendy WS: {e}")
                finally:
                    ping_task.cancel()
        except Exception as e:
            _ws_client = None
            _ws_connected_event.clear()
            reset_discovered_controller_url()
            logger.warning(f"Brak połączenia z Kontrolerem. Ponawiam za 5s... ({e})")
            await asyncio.sleep(5)


def start_ws_client() -> None:
    """Uruchamia pętlę zdarzeń klienta WebSocket w osobnym wątku."""
    global _ws_loop
    _ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_loop)
    _ws_loop.run_until_complete(_ws_client_loop())
