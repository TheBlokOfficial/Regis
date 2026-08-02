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


class ControllerAPIClient:
    """Zarządza połączeniem z Kontrolerem: rejestracja HTTP oraz komunikacja WebSocket."""
    
    def __init__(self):
        self.settings = load_settings()
        self._ws_loop: asyncio.AbstractEventLoop | None = None
        self._ws_client: Any = None

    def reload_settings(self) -> None:
        """Ponownie ładuje ustawienia z dysku, np. gdyby inny proces je zmienił."""
        self.settings = load_settings()

    def get_controller_url(self) -> str:
        """Zwraca adres URL Kontrolera z konfiguracji lub z Discovery (fallback: 127.0.0.1)."""
        url = self.settings.get("controller_url", "auto")
        if url == "auto":
            try:
                return discover_controller()
            except Exception:
                return "http://127.0.0.1:8000"
        return url

    def get_node_id(self) -> str:
        """Zwraca gwarantowane, tekstowe ID klienta."""
        return str(self.settings.get("node_id") or self.settings.get("instance_name") or "client-default")

    def apply_node_config(self, config_data: dict, from_registration: bool = False) -> None:
        """Aplikuje nową konfigurację z Kontrolera dla Klienta."""
        if "name" in config_data:
            self.settings["instance_name"] = config_data["name"]

        services = config_data.get("services", {})

        # 1. Konfiguracja Workera (LLM)
        if "worker" in services:
            w_cfg = services["worker"]
            if "model_name" in w_cfg:
                self.settings["selected_model"] = w_cfg["model_name"]
            if "priority" in w_cfg:
                self.settings["worker_priority"] = w_cfg["priority"]
            self.settings["autostart_worker"] = True
            
            start_service("worker", w_cfg)
        else:
            self.settings["autostart_worker"] = False
            if SERVICES["worker"].is_running():
                stop_service("worker")

        # 2. Konfiguracja Satelity (Audio/VAD)
        if "satellite" in services:
            s_cfg = services["satellite"]
            if "room" in s_cfg:
                self.settings["room"] = s_cfg["room"]
            self.settings["autostart_satellite"] = True
            if not SERVICES["satellite"].is_running():
                start_service("satellite", s_cfg)
        else:
            self.settings["autostart_satellite"] = False
            if SERVICES["satellite"].is_running():
                stop_service("satellite")

        save_settings(self.settings)
        if not from_registration:
            self.register()

    def register(self) -> None:
        """Wysyła zbiorczą rejestrację Aplikacji Klienckiej do Kontrolera."""
        def _do_reg():
            try:
                node_id = self.get_node_id()
                controller_url = self.get_controller_url()
                        
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
                    self.apply_node_config(config_data, from_registration=True)
                    
            except Exception as e:
                print(f"Nie udało się zarejestrować Klienta w Kontrolerze: {e}")

        threading.Thread(target=_do_reg, daemon=True).start()

    def unregister(self) -> None:
        """Wyrejestrowuje Klienta z Kontrolera."""
        try:
            node_id = self.get_node_id()
            controller_url = self.get_controller_url()
            requests.delete(f"{controller_url}/v1/nodes/{node_id}", timeout=2)
            print(f"Wyrejestrowano Klienta '{node_id}' z Kontrolera.")
        except Exception:
            pass

    def bus_publish(self, event: dict) -> None:
        """Wysyła zdarzenie bezpośrednio przez otwarty WebSocket do Kontrolera."""
        if "timestamp" not in event:
            event["timestamp"] = time.strftime("%H:%M:%S")
        
        if self._ws_loop and self._ws_client:
            ws_event = WSSatelliteEvent(
                event_type=event.get("type", "unknown"),
                data=event
            )
            asyncio.run_coroutine_threadsafe(self._ws_client.send(ws_event.model_dump_json()), self._ws_loop)

    async def _handle_ws_message(self, ws: Any, message: str) -> None:
        """Obsługuje pojedynczą wiadomość z Kontrolera przez WebSocket."""
        try:
            data = json.loads(message)
            ws_cmd = WSCommand(**data)
        except Exception as e:
            print(f"Nieprawidłowy format komendy WS: {e}")
            return

        cmd = ws_cmd.command
        payload = ws_cmd.data

        if cmd == "config":
            self.apply_node_config(payload, from_registration=True)
            res = WSCommandResult(command=cmd, success=True)
            await ws.send(res.model_dump_json())
            return

        if cmd == "status":
            status_dict = get_all_services_status()
            status_dict["autostart_worker"] = self.settings.get("autostart_worker", False)
            status_dict["autostart_satellite"] = self.settings.get("autostart_satellite", False)
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

    async def _ws_client_loop(self) -> None:
        node_id = self.get_node_id()
        controller_url = self.get_controller_url()
                
        ws_url = controller_url.replace("http://", "ws://").replace("https://", "wss://") + f"/v1/ws/nodes/{node_id}"
        
        while True:
            try:
                async with websockets.connect(ws_url) as ws:
                    self._ws_client = ws
                    print(f"Połączono z Kontrolerem przez WebSocket ({ws_url}).")
                    
                    async for message in ws:
                        try:
                            await self._handle_ws_message(ws, message)
                        except Exception as e:
                            print(f"Błąd przetwarzania komendy WS: {e}")
            except Exception as e:
                self._ws_client = None
                print(f"Rozłączono z Kontrolerem. Ponawiam za 5s... ({e})")
                await asyncio.sleep(5)

    def start_ws_client(self) -> None:
        """Uruchamia pętlę zdarzeń klienta WebSocket w osobnym wątku."""
        self._ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._ws_loop)
        self._ws_loop.run_until_complete(self._ws_client_loop())


# Globalny instancja Singletona (dla zachowania wstecznej kompatybilności API modułu)
api_client = ControllerAPIClient()

# Aliasy dla zachowania starego API z main.py i satellite.py
bus_publish = api_client.bus_publish
register = api_client.register
unregister = api_client.unregister
start_ws_client = api_client.start_ws_client
