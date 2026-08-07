import os
import json
import logging
import time
import httpx
import threading
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from controller.config import DATA_DIR, SUPPORTED_REGIS_MODELS
from protocol.schemas import (
    ClientRegistrationRequest, ClientConfigRequest,
    WSClientEvent, WSCommandResult
)
import controller.event_bus as event_bus
import controller.registry as registry

router_nodes = APIRouter()

NODES_CONFIG_FILE = os.path.join(DATA_DIR, "nodes_config.json")
_config_lock = threading.Lock()

def load_nodes_config() -> dict:
    with _config_lock:
        if os.path.exists(NODES_CONFIG_FILE):
            with open(NODES_CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}


def save_nodes_config(config_dict: dict) -> None:
    with _config_lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(NODES_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2, ensure_ascii=False)


@router_nodes.get("/v1/clients/supported_models")
async def get_supported_models():
    """Zwraca oficjalną listę wspieranych modeli Regis dla Węzłów Klienckich."""
    return {"models": SUPPORTED_REGIS_MODELS}


@router_nodes.get("/v1/clients/{client_id}/config")
async def get_node_config(client_id: str):
    """Zwraca profil konfiguracji Węzła Klienckiego przechowywany w Kontrolerze."""
    persistent_configs = load_nodes_config()
    if client_id in persistent_configs:
        return persistent_configs[client_id]
    if client_id in registry.node_registry:
        node = registry.node_registry[client_id]
        return {"name": node.get("name"), "services": node.get("services", {})}
    raise HTTPException(status_code=404, detail=f"Klient {client_id} nie został odnaleziony.")


@router_nodes.post("/v1/clients/{client_id}/config")
async def update_node_config(client_id: str, body: ClientConfigRequest):
    """Zapisuje konfigurację Węzła Klienckiego w Kontrolerze i synchronizuje ją przez WS."""
    persistent_configs = load_nodes_config()
    current_profile = persistent_configs.get(client_id, {})

    new_name = body.name if body.name is not None else current_profile.get("name", client_id)
    new_services = body.services if body.services else current_profile.get("services", {})

    updated_profile = {
        "name": new_name,
        "services": new_services,
    }
    persistent_configs[client_id] = updated_profile
    save_nodes_config(persistent_configs)

    if client_id in registry.node_registry:
        success = await registry.node_manager.send_command(client_id, "config", updated_profile)
        if not success:
            # Revert the config if client is unreachable
            persistent_configs[client_id] = current_profile
            save_nodes_config(persistent_configs)
            logging.warning(f"Nie udało się wysłać konfiguracji przez WS do Klienta {client_id}. Zmiany wycofane.")
            raise HTTPException(status_code=502, detail=f"Klient {client_id} jest nieosiągalny (brak połączenia WebSocket). Nie można zaaplikować konfiguracji.")

        # Update in-memory registry only if network push was successful
        registry.node_registry[client_id]["name"] = new_name
        registry.node_registry[client_id]["services"] = new_services

    await event_bus.publish({
        "type": "node_updated",
        "id": client_id,
        "node": registry.node_registry.get(client_id, {"id": client_id, **updated_profile}),
    })

    return {"status": "ok", "config": updated_profile}


@router_nodes.websocket("/v1/ws/clients/{client_id}")
async def websocket_client_endpoint(websocket: WebSocket, client_id: str):
    """Stałe połączenie WebSocket utrzymywane przez Aplikację Kliencką (Single-Step Registration & Events)."""
    node_id = client_id
    await registry.node_manager.connect(node_id, websocket)
    
    # Automatyczny push zapamiętanej konfiguracji po połączeniu
    persistent_configs = load_nodes_config()
    if node_id in persistent_configs:
        stored_profile = persistent_configs[node_id]
        await registry.node_manager.send_command(node_id, "config", stored_profile)

    try:
        while True:
            data = await websocket.receive_json()
            # Zaktualizuj last_seen przy każdym odebranym komunikacie
            if node_id in registry.node_registry:
                registry.node_registry[node_id]["last_seen"] = time.time()
                
            msg_type = data.get("type")

            if msg_type == "register":
                try:
                    reg_payload = data.get("data", {})
                    req = ClientRegistrationRequest(**reg_payload)
                    
                    is_new = req.id not in registry.node_registry
                    incoming_services = req.services

                    persistent_configs = load_nodes_config()
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
                        save_nodes_config(persistent_configs)

                    node_data = {
                        "id": req.id,
                        "name": name,
                        "host": req.host,
                        "services": services_dict,
                        "last_seen": time.time(),
                    }
                    registry.node_registry[req.id] = node_data

                    if is_new:
                        service_names = list(services_dict.keys())
                        logging.info(
                            f"Zarejestrowano Klienta (WebSocket): {req.id} "
                            f"(host={req.host}, usługi={service_names})"
                        )
                        await event_bus.publish({
                            "type": "node_registered",
                            "id": req.id,
                            "node": node_data,
                        })

                    # Odsyłamy profil konfiguracji bezpośrednio w ramce WS
                    await websocket.send_json({
                        "type": "config",
                        "data": {
                            "name": name,
                            "services": services_dict,
                        }
                    })
                except Exception as e:
                    logging.error(f"Błąd rejestracji przez WebSocket dla {node_id}: {e}")

            elif msg_type == "status":
                pass # Status jest trzymany po stronie węzła, heartbeat wystarczy
            elif msg_type == "satellite_event":
                try:
                    event = WSClientEvent(**data)
                    await event_bus.publish({
                        "type": "satellite_event",
                        "satellite_id": node_id,
                        "event_type": event.event_type,
                        "data": event.data,
                    })

                    # Jeśli Satelita wchodzi w stan WAITING, sprawdzamy czy sieć jest gotowa do jej wybudzenia
                    if event.event_type == "state" and event.data.get("state") == "WAITING":
                        audio_nodes = registry.get_audio_nodes()
                        llm_nodes = registry.get_llm_nodes()
                        if audio_nodes and (llm_nodes or providers.has_llm_provider()):
                            await registry.node_manager.send_command(node_id, "satellite_control", {"action": "resume"})
                except Exception as e:
                    logging.error(f"Błąd parsowania WSClientEvent: {e}")
            elif msg_type == "command_result":
                try:
                    res = WSCommandResult(**data)
                    await event_bus.publish({
                        "type": "node_command_result",
                        "node_id": node_id,
                        "command": res.command,
                        "success": res.success,
                        "error": res.error,
                        "result": res.result,
                    })
                except Exception as e:
                    logging.error(f"Błąd parsowania WSCommandResult: {e}")
            elif msg_type == "task_event":
                try:
                    await event_bus.publish({
                        "type": "task_event",
                        "node_id": node_id,
                        "task_id": data.get("task_id"),
                        "event": data.get("event")
                    })
                except Exception as e:
                    logging.error(f"Błąd publikacji task_event: {e}")
            elif msg_type == "wake_check":
                audio_nodes = registry.get_audio_nodes()
                llm_nodes = registry.get_llm_nodes()
                if not audio_nodes:
                    await websocket.send_json({"type": "wake_check_result", "permitted": False, "reason": "Brak dostępnej usługi Audio (STT/TTS)"})
                elif not llm_nodes and not providers.has_llm_provider():
                    await websocket.send_json({"type": "wake_check_result", "permitted": False, "reason": "Brak dostępnych usług LLM"})
                else:
                    await websocket.send_json({"type": "wake_check_result", "permitted": True})
            elif msg_type == "audio_complete":
                # Satelita zakończyła odtwarzanie audio – Kontroler decyduje o powrocie do nasłuchu
                await registry.node_manager.send_command(node_id, "satellite_control", {"action": "resume"})
    except WebSocketDisconnect:
        registry.node_manager.disconnect(node_id)
        if node_id in registry.node_registry:
            del registry.node_registry[node_id]
            logging.info(f"Węzeł {node_id} rozłączył się (WebSocket) i został automatycznie wyrejestrowany.")
            await event_bus.publish({"type": "node_unregistered", "id": node_id})


