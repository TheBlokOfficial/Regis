import json
import logging
from typing import Any, Callable

import client.service_bus as service_bus
from client.network.client_registry import apply_service_config
from client.process_manager import get_all_services_status
from protocol.schemas import WSCommand, WSCommandResult

logger = logging.getLogger(__name__)

_wake_check_callback: Callable[[bool], None] | None = None


def set_wake_check_callback(callback: Callable[[bool], None] | None) -> None:
    global _wake_check_callback
    _wake_check_callback = callback


async def _cmd_config(payload: dict) -> dict:
    apply_service_config(payload, from_registration=True)
    return {"success": True}


async def _cmd_status(payload: dict) -> dict:
    return {"success": True, "result": get_all_services_status()}


SYSTEM_COMMAND_HANDLERS = {
    "config": _cmd_config,
    "status": _cmd_status,
}


async def handle_ws_message(ws: Any, message: str) -> None:
    """Obsługuje pojedynczą wiadomość z Kontrolera przez WebSocket (Dispatcher)."""
    global _wake_check_callback
    try:
        data = json.loads(message)
        
        if data.get("type") == "wake_check_result":
            if _wake_check_callback:
                _wake_check_callback(data.get("permitted", False))
            return

        if data.get("type") == "config":
            apply_service_config(data.get("data", {}), from_registration=True)
            return
            
        ws_cmd = WSCommand(**data)
    except Exception as e:
        logger.warning(f"Nieprawidłowy format komendy WS: {e} ({message})")
        return

    # 1. Komendy systemowe Zarządcy Węzła (config, status)
    handler = SYSTEM_COMMAND_HANDLERS.get(ws_cmd.command)
    
    try:
        if handler:
            response_data = await handler(ws_cmd.data)
        else:
            # 2. Wszystkie pozostałe komendy przekazujemy bezdomenowo do Magistrali Komend Usług (service_bus)
            response_data = await service_bus.dispatch(ws_cmd.command, ws_cmd.data)
            
        success = response_data.get("success", True)
        result = response_data.get("result")
        res = WSCommandResult(command=ws_cmd.command, success=success, result=result)
        await ws.send(res.model_dump_json())
    except Exception as e:
        res = WSCommandResult(command=ws_cmd.command, success=False, error=str(e))
        await ws.send(res.model_dump_json())
