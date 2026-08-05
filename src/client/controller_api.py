import json
import time
from datetime import datetime
import asyncio
import threading
import requests
import websockets
from typing import Any

def _get_timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

from client.config import load_settings, save_settings
from client.process_manager import (
    control_service,
    get_active_services_registration, get_all_services_status
)
from protocol.schemas import (
    WSSatelliteEvent, WSCommand, WSCommandResult, ClientRegistrationRequest,
    ServiceControlPayload, ServiceAction
)
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


_discovered_controller_url: str | None = None

def get_controller_url(allow_fallback: bool = False) -> str:
    """Zwraca adres URL Kontrolera z konfiguracji lub z Discovery."""
    global _discovered_controller_url
    settings = _get_settings()
    url = settings.get("controller_url", "auto")
    
    if url == "auto":
        if _discovered_controller_url:
            return _discovered_controller_url
        try:
            _discovered_controller_url = discover_controller()
            return _discovered_controller_url
        except Exception:
            if allow_fallback:
                return "http://127.0.0.1:8000"
            raise RuntimeError("Nie odnaleziono Kontrolera w sieci (Auto-Discovery).")
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
    active_statuses = get_all_services_status()

    if not from_registration:
        ts = _get_timestamp()
        print(f"[{ts}] [Klient] Zastosowano nową konfigurację z Kontrolera (Web UI).")

    # Konfiguracja poszczególnych mikrousług: llm, audio, satellite
    target_services = ["llm", "audio", "satellite"]
    for s_name in target_services:
        if s_name in services:
            if active_statuses.get(s_name) == "running":
                if not from_registration:
                    control_service(s_name, "restart", services[s_name])
            else:
                control_service(s_name, "start", services[s_name])
        else:
            if active_statuses.get(s_name) == "running":
                control_service(s_name, "stop")
    
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
            ts = _get_timestamp()
            print(f"[{ts}] Aplikacja Kliencka '{node_id}' zarejestrowana w Kontrolerze ({controller_url}).")
            
            config_data = resp.json().get("config")
            if config_data:
                apply_node_config(config_data, from_registration=True)
                
        except Exception as e:
            ts = _get_timestamp()
            print(f"[{ts}] Nie udało się zarejestrować Klienta w Kontrolerze: {e}")

    threading.Thread(target=_do_reg, daemon=True).start()


def unregister() -> None:
    """Wyrejestrowuje Klienta z Kontrolera."""
    try:
        node_id = _get_node_id()
        controller_url = get_controller_url()
        requests.delete(f"{controller_url}/v1/nodes/{node_id}", timeout=2)
        ts = _get_timestamp()
        print(f"[{ts}] Wyrejestrowano Klienta '{node_id}' z Kontrolera.")
    except Exception:
        pass


def bus_publish(event: dict) -> None:
    """Wysyła zdarzenie bezpośrednio przez otwarty WebSocket do Kontrolera."""
    if "timestamp" not in event:
        event["timestamp"] = _get_timestamp()
    
    if _ws_loop and _ws_client:
        ws_event = WSSatelliteEvent(
            event_type=event.get("type", "unknown"),
            data=event
        )
        asyncio.run_coroutine_threadsafe(_ws_client.send(ws_event.model_dump_json()), _ws_loop)


def send_audio_complete() -> None:
    """
    Informuje Kontroler przez WebSocket, że Satelita zakończyła odtwarzanie audio.
    Wywołuje to Kontroler do wysłania komendy start_listening z powrotem do Satelity.
    """
    if _ws_loop and _ws_client:
        msg = json.dumps({"type": "audio_complete"})
        asyncio.run_coroutine_threadsafe(_ws_client.send(msg), _ws_loop)


import client.service_bus as service_bus

# --- Handlery Komend Systemowych Węzła (Node System Commands) ---

async def _cmd_config(payload: dict) -> dict:
    apply_node_config(payload, from_registration=True)
    return {"success": True}

async def _cmd_status(payload: dict) -> dict:
    return {"success": True, "result": get_all_services_status()}

async def _cmd_service_control(payload: dict) -> dict:
    ctrl_req = ServiceControlPayload(**payload)
    success = control_service(ctrl_req.service, ctrl_req.action)
    return {"success": success}

SYSTEM_COMMAND_HANDLERS = {
    "config": _cmd_config,
    "status": _cmd_status,
    "service_control": _cmd_service_control,
}

_wake_check_callback = None

async def request_wake_permission(timeout: float = 2.0) -> bool:
    """Wysyła zapytanie do Kontrolera o pozwolenie na nagrywanie i czeka na odpowiedź."""
    global _wake_check_callback
    if not _ws_loop or not _ws_client:
        return False
        
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    
    def resolve(permitted: bool):
        if not future.done():
            loop.call_soon_threadsafe(future.set_result, permitted)
            
    _wake_check_callback = resolve
    
    try:
        req = {"type": "wake_check"}
        asyncio.run_coroutine_threadsafe(_ws_client.send(json.dumps(req)), _ws_loop)
        
        result = await asyncio.wait_for(future, timeout)
        return result
    except asyncio.TimeoutError:
        print("Timeout podczas oczekiwania na wake_check_result.")
        return False
    except Exception as e:
        print(f"Błąd podczas request_wake_permission: {e}")
        return False
    finally:
        _wake_check_callback = None

async def _handle_ws_message(ws: Any, message: str) -> None:
    """Obsługuje pojedynczą wiadomość z Kontrolera przez WebSocket (Dispatcher)."""
    global _wake_check_callback
    try:
        data = json.loads(message)
        
        if data.get("type") == "wake_check_result":
            if _wake_check_callback:
                _wake_check_callback(data.get("permitted", False))
            return
            
        ws_cmd = WSCommand(**data)
    except Exception as e:
        print(f"Nieprawidłowy format komendy WS: {e} ({message})")
        return

    # 1. Komendy systemowe Zarządcy Węzła (config, status, service_control)
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


def send_task_result(task_id: str, event: dict) -> None:
    """Przesyła zdarzenie/ramkę wyniku z usługi podrzędnej przez WebSocket do Kontrolera."""
    if _ws_client and _ws_loop and _ws_loop.is_running():
        payload = json.dumps({"type": "task_event", "task_id": task_id, "event": event})
        asyncio.run_coroutine_threadsafe(_ws_client.send(payload), _ws_loop)


async def _ws_client_loop() -> None:
    global _ws_client
    
    node_id = _get_node_id()
    
    while True:
        try:
            controller_url = get_controller_url(allow_fallback=False)
            ws_url = controller_url.replace("http://", "ws://").replace("https://", "wss://") + f"/v1/ws/nodes/{node_id}"
            
            async with websockets.connect(ws_url) as ws:
                _ws_client = ws
                ts = _get_timestamp()
                print(f"[{ts}] Połączono z Kontrolerem przez WebSocket ({ws_url}).")
                register()
                
                async for message in ws:
                    try:
                        await _handle_ws_message(ws, message)
                    except Exception as e:
                        ts = _get_timestamp()
                        print(f"[{ts}] Błąd przetwarzania komendy WS: {e}")
        except Exception as e:
            _ws_client = None
            ts = _get_timestamp()
            print(f"[{ts}] Brak połączenia z Kontrolerem. Ponawiam za 5s... ({e})")
            await asyncio.sleep(5)


def start_ws_client() -> None:
    """Uruchamia pętlę zdarzeń klienta WebSocket w osobnym wątku."""
    global _ws_loop
    _ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_loop)
    _ws_loop.run_until_complete(_ws_client_loop())
