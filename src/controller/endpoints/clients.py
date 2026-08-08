import time
import logging
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel

from controller.agent.models import SUPPORTED_REGIS_MODELS
from protocol.schemas import (
    ClientRegistrationRequest,
    ClientConfigRequest,
    WSClientEvent,
    WSCommandResult,
)
import controller.core.client_registry as client_registry
import controller.core.event_bus as event_bus
from controller.config import loader as config
from controller.config.schemas import ClientsConfig

router_clients = APIRouter()


class ClientCommandRequest(BaseModel):
    command: str  # np. service_control, status, config
    data: dict = {}


class ClientConnectionManager:
    """Zarządza aktywnymi połączeniami WebSocket ze Zjednoczonymi Klientami."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str) -> None:
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_command(self, client_id: str, command: str, data: dict = None) -> bool:
        """Wysyła komendę do klienta przez WebSocket. Zwraca True jeśli wysłano pomyślnie."""
        from protocol.schemas import WSCommand
        if client_id in self.active_connections:
            try:
                cmd = WSCommand(command=command, data=data or {})
                await self.active_connections[client_id].send_text(cmd.model_dump_json())
                return True
            except Exception:
                self.disconnect(client_id)
        return False


client_manager = ClientConnectionManager()


def _get_persistent_clients() -> dict:
    return config.load(ClientsConfig).root


def _save_persistent_clients(clients_dict: dict) -> None:
    config.save(ClientsConfig(clients_dict))


async def send_client_command(client_id: str, command: str, payload: dict) -> dict:
    client = client_registry.client_registry.get(client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Klient '{client_id}' nie jest zarejestrowany.")

    success = await client_manager.send_command(client_id, command, payload)
    if not success:
        error_msg = f"Klient {client_id} jest nieosiągalny (brak aktywnego połączenia WebSocket)."
        logging.warning(f"[Clients] Komenda '{command}' do klienta '{client_id}' nie powiodła się: {error_msg}")
        await event_bus.publish({
            "type": "client_command_result",
            "client_id": client_id,
            "command": command,
            "success": False,
            "error": error_msg,
        })
        raise HTTPException(status_code=502, detail=error_msg)

    logging.info(f"[Clients] Komenda '{command}' wysłana do klienta '{client_id}' przez WS.")
    return {"status": "pending", "client_id": client_id, "command": command}


@router_clients.get("/v1/clients/supported_models")
async def get_supported_models():
    """Zwraca oficjalną listę wspieranych modeli Regis dla Klientów."""
    return {"models": SUPPORTED_REGIS_MODELS}


@router_clients.post("/v1/clients/{client_id}/command")
@router_clients.post("/api/node/{client_id}/command")  # Alias dla wstecznej kompatybilności z UI
async def send_client_command_endpoint(client_id: str, body: ClientCommandRequest):
    """Wysyła komendę do Aplikacji Klienckiej przez aktywny tunel WebSocket."""
    return await send_client_command(client_id, body.command, body.data)


@router_clients.get("/v1/clients/{client_id}/config")
async def get_client_config(client_id: str):
    """Zwraca profil konfiguracji Klienta przechowywany w Kontrolerze."""
    persistent_configs = _get_persistent_clients()
    if client_id in persistent_configs:
        return persistent_configs[client_id]
    if client_id in client_registry.client_registry:
        client = client_registry.client_registry[client_id]
        return {"name": client.get("name"), "services": client.get("services", {})}
    raise HTTPException(status_code=404, detail=f"Klient {client_id} nie został odnaleziony.")


@router_clients.post("/v1/clients/{client_id}/config")
async def update_client_config(client_id: str, body: ClientConfigRequest):
    """Zapisuje konfigurację Klienta w Kontrolerze i synchronizuje ją przez WebSocket."""
    persistent_configs = _get_persistent_clients()
    current_profile = persistent_configs.get(client_id, {})

    new_name = body.name if body.name is not None else current_profile.get("name", client_id)
    new_services = body.services if body.services else current_profile.get("services", {})

    updated_profile = {
        "name": new_name,
        "services": new_services,
    }
    persistent_configs[client_id] = updated_profile
    _save_persistent_clients(persistent_configs)

    if client_id in client_registry.client_registry:
        success = await client_manager.send_command(client_id, "config", updated_profile)
        if not success:
            persistent_configs[client_id] = current_profile
            _save_persistent_clients(persistent_configs)
            logging.warning(f"Nie udało się wysłać konfiguracji przez WS do Klienta {client_id}. Zmiany wycofane.")
            raise HTTPException(
                status_code=502,
                detail=f"Klient {client_id} jest nieosiągalny (brak połączenia WebSocket). Nie można zaaplikować konfiguracji."
            )

        client_registry.client_registry[client_id]["name"] = new_name
        client_registry.client_registry[client_id]["services"] = new_services

    await event_bus.publish({
        "type": "client_updated",
        "id": client_id,
        "client": client_registry.client_registry.get(client_id, {"id": client_id, **updated_profile}),
    })

    return {"status": "ok", "config": updated_profile}


# ─── Obsługa Wiadomości WebSocket ─────────────────────────────────────────────

async def _handle_ws_register(client_id: str, data: dict, websocket: WebSocket):
    try:
        reg_payload = data.get("data", {})
        req = ClientRegistrationRequest(**reg_payload)

        is_new = req.id not in client_registry.client_registry
        incoming_services = req.services

        persistent_configs = _get_persistent_clients()
        stored_profile = persistent_configs.get(req.id)

        if stored_profile:
            name = stored_profile.get("name", req.name or req.id)
            services_dict = stored_profile.get("services", incoming_services)
        else:
            name = req.name or req.id
            services_dict = incoming_services
            persistent_configs[req.id] = {
                "name": name,
                "services": services_dict,
            }
            _save_persistent_clients(persistent_configs)

        client_data = {
            "id": req.id,
            "name": name,
            "host": req.host,
            "services": services_dict,
            "last_seen": time.time(),
        }
        client_registry.client_registry[req.id] = client_data

        if is_new:
            service_names = list(services_dict.keys())
            logging.info(
                f"Zarejestrowano Klienta (WebSocket): {req.id} "
                f"(host={req.host}, usługi={service_names})"
            )
            await event_bus.publish({
                "type": "client_registered",
                "id": req.id,
                "client": client_data,
            })

        await websocket.send_json({
            "type": "config",
            "data": {
                "name": name,
                "services": services_dict,
            }
        })
    except Exception as e:
        logging.error(f"Błąd rejestracji przez WebSocket dla {client_id}: {e}")

async def _handle_ws_satellite_event(client_id: str, data: dict, websocket: WebSocket):
    try:
        event = WSClientEvent(**data)
        await event_bus.publish({
            "type": "satellite_event",
            "satellite_id": client_id,
            "event_type": event.event_type,
            "data": event.data,
        })

        if event.event_type == "state" and event.data.get("state") == "WAITING":
            import controller.providers.llm.resolver as providers
            audio_clients = client_registry.get_audio_clients()
            llm_clients = client_registry.get_llm_clients()
            if audio_clients and (llm_clients or providers.has_llm_provider()):
                await client_manager.send_command(client_id, "satellite_control", {"action": "resume"})
    except Exception as e:
        logging.error(f"Błąd parsowania WSClientEvent: {e}")

async def _handle_ws_command_result(client_id: str, data: dict, websocket: WebSocket):
    try:
        res = WSCommandResult(**data)
        await event_bus.publish({
            "type": "client_command_result",
            "client_id": client_id,
            "command": res.command,
            "success": res.success,
            "error": res.error,
            "result": res.result,
        })
    except Exception as e:
        logging.error(f"Błąd parsowania WSCommandResult: {e}")

async def _handle_ws_task_event(client_id: str, data: dict, websocket: WebSocket):
    try:
        task_id = data.get("task_id")
        event_data = data.get("event", {})
        if task_id:
            from controller.providers.llm.client_app import route_task_event
            route_task_event(task_id, event_data)
        else:
            logging.warning(f"Odebrano task_event bez task_id od klienta {client_id}")
    except Exception as e:
        logging.error(f"Błąd obsługi task_event: {e}")

async def _handle_ws_wake_check(client_id: str, data: dict, websocket: WebSocket):
    import controller.providers.llm.resolver as providers
    audio_clients = client_registry.get_audio_clients()
    llm_clients = client_registry.get_llm_clients()
    if not audio_clients:
        await websocket.send_json({"type": "wake_check_result", "permitted": False, "reason": "Brak dostępnej usługi Audio (STT/TTS)"})
    elif not llm_clients and not providers.has_llm_provider():
        await websocket.send_json({"type": "wake_check_result", "permitted": False, "reason": "Brak dostępnych usług LLM"})
    else:
        await websocket.send_json({"type": "wake_check_result", "permitted": True})

async def _handle_ws_audio_complete(client_id: str, data: dict, websocket: WebSocket):
    await client_manager.send_command(client_id, "satellite_control", {"action": "resume"})

WS_EVENT_HANDLERS = {
    "register": _handle_ws_register,
    "satellite_event": _handle_ws_satellite_event,
    "client_event": _handle_ws_satellite_event,
    "command_result": _handle_ws_command_result,
    "task_event": _handle_ws_task_event,
    "wake_check": _handle_ws_wake_check,
    "audio_complete": _handle_ws_audio_complete,
    "status": lambda c, d, w: None,
}

async def handle_ws_message(client_id: str, data: dict, websocket: WebSocket):
    msg_type = data.get("type")
    handler = WS_EVENT_HANDLERS.get(msg_type)
    if handler:
        result = handler(client_id, data, websocket)
        if asyncio.iscoroutine(result):
            await result
    else:
        logging.warning(f"Otrzymano nieznany typ wiadomości od {client_id}: {msg_type}")


@router_clients.websocket("/v1/ws/clients/{client_id}")
async def websocket_client_endpoint(websocket: WebSocket, client_id: str):
    """Stałe połączenie WebSocket utrzymywane przez Aplikację Kliencką (Single-Step Registration & Events)."""
    await client_manager.connect(client_id, websocket)

    # Push zapamiętanej konfiguracji po połączeniu
    persistent_configs = _get_persistent_clients()
    if client_id in persistent_configs:
        stored_profile = persistent_configs[client_id]
        await client_manager.send_command(client_id, "config", stored_profile)

    try:
        while True:
            data = await websocket.receive_json()
            if client_id in client_registry.client_registry:
                client_registry.client_registry[client_id]["last_seen"] = time.time()

            await handle_ws_message(client_id, data, websocket)

    except WebSocketDisconnect:
        client_manager.disconnect(client_id)
        if client_id in client_registry.client_registry:
            del client_registry.client_registry[client_id]
            logging.info(f"Klient {client_id} rozłączył się (WebSocket) i został automatycznie wyrejestrowany.")
            await event_bus.publish({"type": "client_unregistered", "id": client_id})
