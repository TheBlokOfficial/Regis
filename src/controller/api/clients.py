import json
import logging
import time
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from controller.llm.models import SUPPORTED_REGIS_MODELS
from protocol.schemas import (
    ClientRegistrationRequest, ClientConfigRequest,
    WSClientEvent, WSCommandResult
)
import controller.core.event_bus as event_bus
import controller.core.client_store as client_store
import controller.llm.providers as providers
from controller.core.connection_manager import client_manager

router_clients = APIRouter()

@router_clients.get("/v1/clients/supported_models")
async def get_supported_models():
    """Zwraca oficjalną listę wspieranych modeli Regis dla Klientów."""
    return {"models": SUPPORTED_REGIS_MODELS}


@router_clients.get("/v1/clients/{client_id}/config")
async def get_client_config(client_id: str):
    """Zwraca profil konfiguracji Klienta przechowywany w Kontrolerze."""
    persistent_configs = client_store.load_persistent_clients()
    if client_id in persistent_configs:
        return persistent_configs[client_id]
    if client_id in client_store.client_registry:
        client = client_store.client_registry[client_id]
        return {"name": client.get("name"), "services": client.get("services", {})}
    raise HTTPException(status_code=404, detail=f"Klient {client_id} nie został odnaleziony.")


@router_clients.post("/v1/clients/{client_id}/config")
async def update_client_config(client_id: str, body: ClientConfigRequest):
    """Zapisuje konfigurację Klienta w Kontrolerze i synchronizuje ją przez WebSocket."""
    persistent_configs = client_store.load_persistent_clients()
    current_profile = persistent_configs.get(client_id, {})

    new_name = body.name if body.name is not None else current_profile.get("name", client_id)
    new_services = body.services if body.services else current_profile.get("services", {})

    updated_profile = {
        "name": new_name,
        "services": new_services,
    }
    persistent_configs[client_id] = updated_profile
    client_store.save_persistent_clients(persistent_configs)

    if client_id in client_store.client_registry:
        success = await client_manager.send_command(client_id, "config", updated_profile)
        if not success:
            persistent_configs[client_id] = current_profile
            client_store.save_persistent_clients(persistent_configs)
            logging.warning(f"Nie udało się wysłać konfiguracji przez WS do Klienta {client_id}. Zmiany wycofane.")
            raise HTTPException(
                status_code=502,
                detail=f"Klient {client_id} jest nieosiągalny (brak połączenia WebSocket). Nie można zaaplikować konfiguracji."
            )

        client_store.client_registry[client_id]["name"] = new_name
        client_store.client_registry[client_id]["services"] = new_services

    await event_bus.publish({
        "type": "client_updated",
        "id": client_id,
        "client": client_store.client_registry.get(client_id, {"id": client_id, **updated_profile}),
    })

    return {"status": "ok", "config": updated_profile}


@router_clients.websocket("/v1/ws/clients/{client_id}")
async def websocket_client_endpoint(websocket: WebSocket, client_id: str):
    """Stałe połączenie WebSocket utrzymywane przez Aplikację Kliencką (Single-Step Registration & Events)."""
    await client_manager.connect(client_id, websocket)

    # Push zapamiętanej konfiguracji po połączeniu
    persistent_configs = client_store.load_persistent_clients()
    if client_id in persistent_configs:
        stored_profile = persistent_configs[client_id]
        await client_manager.send_command(client_id, "config", stored_profile)

    try:
        while True:
            data = await websocket.receive_json()
            if client_id in client_store.client_registry:
                client_store.client_registry[client_id]["last_seen"] = time.time()

            msg_type = data.get("type")

            if msg_type == "register":
                try:
                    reg_payload = data.get("data", {})
                    req = ClientRegistrationRequest(**reg_payload)

                    is_new = req.id not in client_store.client_registry
                    incoming_services = req.services

                    persistent_configs = client_store.load_persistent_clients()
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
                        client_store.save_persistent_clients(persistent_configs)

                    client_data = {
                        "id": req.id,
                        "name": name,
                        "host": req.host,
                        "services": services_dict,
                        "last_seen": time.time(),
                    }
                    client_store.client_registry[req.id] = client_data

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

            elif msg_type == "status":
                pass
            elif msg_type in ("satellite_event", "client_event"):
                try:
                    event = WSClientEvent(**data)
                    await event_bus.publish({
                        "type": "satellite_event",
                        "satellite_id": client_id,
                        "event_type": event.event_type,
                        "data": event.data,
                    })

                    if event.event_type == "state" and event.data.get("state") == "WAITING":
                        audio_clients = client_store.get_audio_clients()
                        llm_clients = client_store.get_llm_clients()
                        if audio_clients and (llm_clients or providers.has_llm_provider()):
                            await client_manager.send_command(client_id, "satellite_control", {"action": "resume"})
                except Exception as e:
                    logging.error(f"Błąd parsowania WSClientEvent: {e}")
            elif msg_type == "command_result":
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
            elif msg_type == "task_event":
                try:
                    task_id = data.get("task_id")
                    event_data = data.get("event", {})
                    if task_id:
                        # Przekieruj do oczekującego worker pipeline zamiast ślepej publikacji
                        from controller.llm.pipeline.worker import route_task_event
                        route_task_event(task_id, event_data)
                    else:
                        logging.warning(f"Odebrano task_event bez task_id od klienta {client_id}")
                except Exception as e:
                    logging.error(f"Błąd obsługi task_event: {e}")
            elif msg_type == "wake_check":
                audio_clients = client_store.get_audio_clients()
                llm_clients = client_store.get_llm_clients()
                if not audio_clients:
                    await websocket.send_json({"type": "wake_check_result", "permitted": False, "reason": "Brak dostępnej usługi Audio (STT/TTS)"})
                elif not llm_clients and not providers.has_llm_provider():
                    await websocket.send_json({"type": "wake_check_result", "permitted": False, "reason": "Brak dostępnych usług LLM"})
                else:
                    await websocket.send_json({"type": "wake_check_result", "permitted": True})
            elif msg_type == "audio_complete":
                await client_manager.send_command(client_id, "satellite_control", {"action": "resume"})
    except WebSocketDisconnect:
        client_manager.disconnect(client_id)
        if client_id in client_store.client_registry:
            del client_store.client_registry[client_id]
            logging.info(f"Klient {client_id} rozłączył się (WebSocket) i został automatycznie wyrejestrowany.")
            await event_bus.publish({"type": "client_unregistered", "id": client_id})
