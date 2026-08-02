import json
import time
import asyncio
import threading
import requests
import websockets
from typing import Any

from client.config import load_settings, save_settings
from client.process_manager import (
    SERVICES, start_service, stop_service, 
    get_active_services_registration, get_all_services_status
)
from protocol.schemas import WSSatelliteEvent, WSCommand, WSCommandResult, ClientRegistrationRequest
from protocol.discovery import get_local_ip, discover_controller

# --- Stan modułu (Pythonic Module Singleton) ---
_settings_cache: dict | None = None
_ws_loop: asyncio.AbstractEventLoop | None = None
_ws_client: Any = None


def _get_settings() -> dict:
    """Zwraca podręczną pamięć ustawień z RAM. Wczytuje z dysku tylko za pierwszym razem."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_settings()
    return _settings_cache


def reload_settings() -> None:
    """Wymusza odświeżenie pamięci podręcznej z dysku."""
    global _settings_cache
    _settings_cache = load_settings()


def get_controller_url() -> str:
    """Zwraca adres URL Kontrolera z konfiguracji lub z Discovery (fallback: 127.0.0.1)."""
    settings = _get_settings()
    url = settings.get("controller_url", "auto")
    if url == "auto":
        try:
            return discover_controller()
        except Exception:
            return "http://127.0.0.1:8000"
    return url


def _get_node_id() -> str:
    """Zwraca gwarantowane, tekstowe ID klienta."""
    settings = _get_settings()
    return str(settings.get("node_id") or settings.get("instance_name") or "client-default")


def apply_node_config(config_data: dict, from_registration: bool = False) -> None:
    """Aplikuje nową konfigurację z Kontrolera dla Klienta."""
    # Zapisz tylko imię (jeśli uległo zmianie) – to element tożsamości
    if "name" in config_data:
        settings = _get_settings()
        if settings.get("instance_name") != config_data["name"]:
            settings["instance_name"] = config_data["name"]
            save_settings(settings)

    services = config_data.get("services", {})

    # 1. Konfiguracja Workera (LLM)
    if "worker" in services:
        start_service("worker", services["worker"])
    else:
        if SERVICES["worker"].is_running():
            stop_service("worker")

    # 2. Konfiguracja Satelity (Audio/VAD)
    if "satellite" in services:
        if not SERVICES["satellite"].is_running():
            start_service("satellite", services["satellite"])
    else:
        if SERVICES["satellite"].is_running():
            stop_service("satellite")
    
    if not from_registration:
        register()


def register() -> None:
    """Wysyła zbiorczą rejestrację Aplikacji Klienckiej do Kontrolera."""
    def _do_reg():
        try:
            node_id = _get_node_id()
            controller_url = get_controller_url()
                    
            reg_request = ClientRegistrationRequest(
                id=node_id,
                name=node_id,
                host=get_local_ip(),
                services=get_active_services_registration(),
            )
            resp = requests.post(f"{controller_url}/v1/nodes/register", json=reg_request.model_dump(), timeout=5)
            resp.raise_for_status()
            print(f"Aplikacja Kliencka '{node_id}' zarejestrowana w Kontrolerze ({controller_url}).")
            
            config_data = resp.json().get("config")
            if config_data:
                apply_node_config(config_data, from_registration=True)
                
        except Exception as e:
            print(f"Nie udało się zarejestrować Klienta w Kontrolerze: {e}")

    threading.Thread(target=_do_reg, daemon=True).start()


def unregister() -> None:
    """Wyrejestrowuje Klienta z Kontrolera."""
    try:
        node_id = _get_node_id()
        controller_url = get_controller_url()
        requests.delete(f"{controller_url}/v1/nodes/{node_id}", timeout=2)
        print(f"Wyrejestrowano Klienta '{node_id}' z Kontrolera.")
    except Exception:
        pass


def bus_publish(event: dict) -> None:
    """Wysyła zdarzenie bezpośrednio przez otwarty WebSocket do Kontrolera."""
    if "timestamp" not in event:
        event["timestamp"] = time.strftime("%H:%M:%S")
    
    if _ws_loop and _ws_client:
        ws_event = WSSatelliteEvent(
            event_type=event.get("type", "unknown"),
            data=event
        )
        asyncio.run_coroutine_threadsafe(_ws_client.send(ws_event.model_dump_json()), _ws_loop)


# --- Handlery Komend (Command Registry) ---

async def _cmd_config(payload: dict) -> dict:
    apply_node_config(payload, from_registration=True)
    return {"success": True}

async def _cmd_status(payload: dict) -> dict:
    return {"success": True, "result": get_all_services_status()}

async def _cmd_service_control(payload: dict) -> dict:
    service = payload.get("service")
    action = payload.get("action")
    if action == "start":
        return {"success": start_service(service)}
    elif action == "stop":
        stop_service(service)
        return {"success": True}
    return {"success": False, "error": f"Nieznana akcja: {action} dla usługi {service}"}

COMMAND_HANDLERS = {
    "config": _cmd_config,
    "status": _cmd_status,
    "service_control": _cmd_service_control,
}

async def _handle_ws_message(ws: Any, message: str) -> None:
    """Obsługuje pojedynczą wiadomość z Kontrolera przez WebSocket (Dispatcher)."""
    try:
        data = json.loads(message)
        ws_cmd = WSCommand(**data)
    except Exception as e:
        print(f"Nieprawidłowy format komendy WS: {e}")
        return

    handler = COMMAND_HANDLERS.get(ws_cmd.command)
    if not handler:
        res = WSCommandResult(command=ws_cmd.command, success=False, error=f"Nieznana komenda: {ws_cmd.command}")
        await ws.send(res.model_dump_json())
        return

    try:
        response_data = await handler(ws_cmd.data)
        success = response_data.get("success", True)
        result = response_data.get("result")
        res = WSCommandResult(command=ws_cmd.command, success=success, result=result)
        await ws.send(res.model_dump_json())
    except Exception as e:
        res = WSCommandResult(command=ws_cmd.command, success=False, error=str(e))
        await ws.send(res.model_dump_json())


async def _ws_client_loop() -> None:
    global _ws_client
    
    node_id = _get_node_id()
    controller_url = get_controller_url()
            
    ws_url = controller_url.replace("http://", "ws://").replace("https://", "wss://") + f"/v1/ws/nodes/{node_id}"
    
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                _ws_client = ws
                print(f"Połączono z Kontrolerem przez WebSocket ({ws_url}).")
                
                async for message in ws:
                    try:
                        await _handle_ws_message(ws, message)
                    except Exception as e:
                        print(f"Błąd przetwarzania komendy WS: {e}")
        except Exception as e:
            _ws_client = None
            print(f"Rozłączono z Kontrolerem. Ponawiam za 5s... ({e})")
            await asyncio.sleep(5)


def start_ws_client() -> None:
    """Uruchamia pętlę zdarzeń klienta WebSocket w osobnym wątku."""
    global _ws_loop
    _ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_loop)
    _ws_loop.run_until_complete(_ws_client_loop())
