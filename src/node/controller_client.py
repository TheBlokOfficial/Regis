import json
import time
import asyncio
import threading
import requests
import websockets
from node.config import load_settings, save_settings
from node.process_manager import (
    SERVICES, start_service, stop_service, 
    get_active_services_registration, get_all_services_status
)

from typing import Any

_ws_loop: asyncio.AbstractEventLoop | None = None
_ws_client: Any = None


def bus_publish(event: dict) -> None:
    """Wysyła zdarzenie bezpośrednio przez otwarty WebSocket do Kontrolera."""
    if "timestamp" not in event:
        event["timestamp"] = time.strftime("%H:%M:%S")
    
    if _ws_loop and _ws_client:
        payload = json.dumps({
            "type": "satellite_event",
            "event_type": event.get("type", "unknown"),
            "data": event
        }, ensure_ascii=False)
        asyncio.run_coroutine_threadsafe(_ws_client.send(payload), _ws_loop)





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
    """Wysyła zbiorczą rejestrację Zjednoczonego Węzła do Kontrolera."""
    def _do_reg():
        try:
            from core.discovery import discover_controller, get_local_ip
            
            settings = load_settings()
            node_id = settings.get("node_id", settings.get("instance_name", "node-default"))
            controller_url = settings.get("controller_url", "auto")
            if controller_url == "auto":
                try:
                    controller_url = discover_controller()
                except Exception:
                    controller_url = "http://192.168.0.119:8000"
                    
            payload = {
                "id": node_id,
                "name": node_id,
                "host": get_local_ip(),
                "port": 8099,
                "services": get_active_services_registration(),
            }
            resp = requests.post(f"{controller_url}/v1/nodes/register", json=payload, timeout=5)
            resp.raise_for_status()
            print(f"Zjednoczony Węzeł '{node_id}' zarejestrowany w Kontrolerze ({controller_url}).")
            
            config_data = resp.json().get("config")
            if config_data:
                apply_node_config(config_data, from_registration=True)
                
        except Exception as e:
            print(f"Nie udało się zarejestrować Węzła w Kontrolerze: {e}")

    threading.Thread(target=_do_reg, daemon=True).start()


def unregister() -> None:
    """Wyrejestrowuje Węzeł z Kontrolera."""
    try:
        from core.discovery import discover_controller
        settings = load_settings()
        node_id = settings.get("node_id", settings.get("instance_name", "node-default"))
        controller_url = settings.get("controller_url", "auto")
        if controller_url == "auto":
            try:
                controller_url = discover_controller()
            except Exception:
                controller_url = "http://192.168.0.119:8000"
        requests.delete(f"{controller_url}/v1/nodes/{node_id}", timeout=2)
        print(f"Wyrejestrowano Zjednoczony Węzeł '{node_id}' z Kontrolera.")
    except Exception:
        pass


async def _handle_ws_message(ws: Any, message: str) -> None:
    """Obsługuje pojedynczą wiadomość z Kontrolera przez WebSocket."""
    data = json.loads(message)
    cmd = data.get("command", "")
    payload = data.get("data", {})

    if cmd == "config":
        apply_node_config(payload, from_registration=True)
        await ws.send(json.dumps({"type": "command_result", "command": cmd, "success": True}))
        return

    if cmd == "status":
        status_dict = get_all_services_status()
        status_dict["autostart_worker"] = load_settings().get("autostart_worker", False)
        status_dict["autostart_satellite"] = load_settings().get("autostart_satellite", False)
        await ws.send(json.dumps({
            "type": "command_result", 
            "command": cmd, 
            "success": True, 
            "result": status_dict
        }))
        return

    # Generyczna obsługa komend dynamicznych: <service_name>_start / <service_name>_stop
    if "_" in cmd:
        srv_name, action = cmd.rsplit("_", 1)
        if action == "start":
            success = start_service(srv_name)
            await ws.send(json.dumps({"type": "command_result", "command": cmd, "success": success}))
            return
        elif action == "stop":
            stop_service(srv_name)
            await ws.send(json.dumps({"type": "command_result", "command": cmd, "success": True}))
            return


async def _ws_client_loop() -> None:
    global _ws_client
    settings = load_settings()
    node_id = settings.get("node_id", settings.get("instance_name", "node-default"))
    controller_url = settings.get("controller_url", "auto")
    if controller_url == "auto":
        try:
            from core.discovery import discover_controller
            controller_url = discover_controller()
        except Exception:
            controller_url = "http://192.168.0.119:8000"
            
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
