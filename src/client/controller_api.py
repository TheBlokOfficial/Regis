import json
import time
import asyncio
import threading
import requests
import websockets
from client.config import load_settings, save_settings
from client.process_manager import (
    SERVICES, start_service, stop_service, 
    get_active_services_registration, get_all_services_status
)
from protocol.schemas import WSSatelliteEvent, WSCommand, WSCommandResult

from typing import Any

_ws_loop: asyncio.AbstractEventLoop | None = None
_ws_client: Any = None


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


def get_controller_url() -> str:
    """Zwraca adres URL Kontrolera z konfiguracji lub z Discovery (fallback: 127.0.0.1)."""
    settings = load_settings()
    url = settings.get("controller_url", "auto")
    if url == "auto":
        try:
            from protocol.discovery import discover_controller
            return discover_controller()
        except Exception:
            return "http://127.0.0.1:8000"
    return url
def apply_node_config(config_data: dict, from_registration: bool = False) -> None:
    """Aplikuje nową konfigurację z Kontrolera dla Węzła."""
    settings = load_settings()

    if "name" in config_data:
        settings["instance_name"] = config_data["name"]

    services = config_data.get("services", {})

    # 1. Konfiguracja Workera (LLM)
    if "worker" in services:
        w_cfg = services["worker"]
        if "model_name" in w_cfg:
            settings["selected_model"] = w_cfg["model_name"]
        if "priority" in w_cfg:
            settings["worker_priority"] = w_cfg["priority"]
        settings["autostart_worker"] = True
        
        start_service("worker", w_cfg)
    else:
        settings["autostart_worker"] = False
        if SERVICES["worker"].is_running():
            stop_service("worker")

    # 2. Konfiguracja Satelity (Audio/VAD)
    if "satellite" in services:
        s_cfg = services["satellite"]
        if "room" in s_cfg:
            settings["room"] = s_cfg["room"]
        settings["autostart_satellite"] = True
        if not SERVICES["satellite"].is_running():
            start_service("satellite", s_cfg)
    else:
        settings["autostart_satellite"] = False
        if SERVICES["satellite"].is_running():
            stop_service("satellite")

    save_settings(settings)
    if not from_registration:
        register()


def register() -> None:
    """Wysyła zbiorczą rejestrację Aplikacji Klienckiej do Kontrolera."""
    def _do_reg():
        try:
            from protocol.discovery import get_local_ip
            from protocol.schemas import ClientRegistrationRequest
            
            settings = load_settings()
            node_id = str(settings.get("node_id") or settings.get("instance_name") or "client-default")
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
        settings = load_settings()
        node_id = str(settings.get("node_id") or settings.get("instance_name") or "client-default")
        controller_url = get_controller_url()
        requests.delete(f"{controller_url}/v1/nodes/{node_id}", timeout=2)
        print(f"Wyrejestrowano Klienta '{node_id}' z Kontrolera.")
    except Exception:
        pass


async def _handle_ws_message(ws: Any, message: str) -> None:
    """Obsługuje pojedynczą wiadomość z Kontrolera przez WebSocket."""
    # Walidacja przychodzącej komendy
    try:
        data = json.loads(message)
        ws_cmd = WSCommand(**data)
    except Exception as e:
        print(f"Nieprawidłowy format komendy WS: {e}")
        return

    cmd = ws_cmd.command
    payload = ws_cmd.data

    if cmd == "config":
        apply_node_config(payload, from_registration=True)
        res = WSCommandResult(command=cmd, success=True)
        await ws.send(res.model_dump_json())
        return

    if cmd == "status":
        status_dict = get_all_services_status()
        status_dict["autostart_worker"] = load_settings().get("autostart_worker", False)
        status_dict["autostart_satellite"] = load_settings().get("autostart_satellite", False)
        res = WSCommandResult(command=cmd, success=True, result=status_dict)
        await ws.send(res.model_dump_json())
        return

    # Generyczna obsługa komend dynamicznych: <service_name>_start / <service_name>_stop
    if "_" in cmd:
        srv_name, action = cmd.rsplit("_", 1)
        if action == "start":
            success = start_service(srv_name)
            res = WSCommandResult(command=cmd, success=success)
            await ws.send(res.model_dump_json())
            return
        elif action == "stop":
            stop_service(srv_name)
            res = WSCommandResult(command=cmd, success=True)
            await ws.send(res.model_dump_json())
            return


async def _ws_client_loop() -> None:
    global _ws_client
    settings = load_settings()
    node_id = str(settings.get("node_id") or settings.get("instance_name") or "client-default")
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
