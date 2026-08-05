"""
Generyczna Magistrala Komend Usług (Service Command Bus) dla Aplikacji Klienckiej.

Umożliwia bezdomenowy routing komend z magistrali Kontrolera (WebSocket)
do odpowiednich lokalnych usług uruchomionych pod Klientem (np. Satelita, Worker itp.).

Zarządca Klienta (src/client/) nie zna szczegółów komend ani domen poszczególnych usług.
 Usługi mogą rejestrować własne handlery lub odbierać komendy przez kolejkowanie.
"""
import asyncio
import logging
from typing import Callable, Any, Optional

_queue: Optional[asyncio.Queue] = None
_loop: Optional[asyncio.AbstractEventLoop] = None
_handlers: dict[str, Callable[[dict], Any]] = {}


def init(loop: asyncio.AbstractEventLoop) -> None:
    """Inicjalizuje magistralę komend. Wywoływane przy starcie klienta/proxy."""
    global _queue, _loop
    _loop = loop
    _queue = asyncio.Queue()


def register_handler(command_name: str, handler: Callable[[dict], Any]) -> None:
    """Rejestruje handler komendy specyficzny dla wybranej usługi."""
    _handlers[command_name] = handler


def unregister_handler(command_name: str) -> None:
    """Wyrejestrowuje handler komendy."""
    _handlers.pop(command_name, None)


async def dispatch(command_name: str, payload: dict) -> dict:
    """
    Kieruje komendę do zarejestrowanego handlera. Jeśli handler nie istnieje,
    przekazuje komendę do ogólnej kolejki (np. dla usług odbierających przez SSE).
    """
    if command_name in _handlers:
        handler = _handlers[command_name]
        try:
            if asyncio.iscoroutinefunction(handler):
                return await handler(payload)
            else:
                return handler(payload)
        except Exception as e:
            logging.error(f"Błąd wykonania handlera dla komendy '{command_name}': {e}")
            return {"success": False, "error": str(e)}

    # Domyślny fallback: wrzuć do kolejki komend usług
    push_command({"command": command_name, **payload})
    return {"success": True}


def push_command(cmd_dict: dict) -> None:
    """
    Wrzuca komendę do kolejki (thread-safe, wywoływalne z dowolnego wątku).
    """
    if _loop and _queue:
        asyncio.run_coroutine_threadsafe(_queue.put(cmd_dict), _loop)


async def get_command() -> Optional[dict]:
    """Pobiera komendę z kolejki. Używane przez endpointy streamingowe usług (np. /internal/service_commands)."""
    if _queue:
        return await _queue.get()
    await asyncio.sleep(0.5)
    return None
