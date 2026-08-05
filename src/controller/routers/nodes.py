import os
import json
import logging
import time
import httpx
import threading
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from controller.config import DATA_DIR
from protocol.schemas import (
    ClientRegistrationRequest, ClientConfigRequest, SUPPORTED_REGIS_MODELS,
    WSSatelliteEvent, WSCommandResult
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


@router_nodes.get("/v1/nodes/supported_models")
async def get_supported_models():
    """Zwraca oficjalną listę wspieranych modeli Regis dla Węzłów."""
    return {"models": SUPPORTED_REGIS_MODELS}


@router_nodes.post("/v1/nodes/register")
async def register_node(request: ClientRegistrationRequest):
    """Rejestruje Zjednoczony Węzeł w Kontrolerze (Node-Service Composition & SSOT Sync)."""
    is_new = request.id not in registry.node_registry
    incoming_services = request.get_normalized_services()

    # Sprawdź, czy w rejestrze Kontrolera (nodes_config.json) istnieje zapisany profil dla tego Węzła
    persistent_configs = load_nodes_config()
    stored_profile = persistent_configs.get(request.id)

    if stored_profile:
        name = stored_profile.get("name", request.name or request.id)
        services_dict = stored_profile.get("services", incoming_services)
    else:
        name = request.name or request.id
        services_dict = incoming_services
        persistent_configs[request.id] = {
            "name": name,
            "services": services_dict,
        }
        save_nodes_config(persistent_configs)

    node_data = {
        # ── 1. Tożsamość i Połączenie (Agnostyczny Węzeł) ──
        "id": request.id,
        "name": name,
        "host": request.host,
        "port": request.port,

        # ── 2. Pakiety Świadczonych Usług ──
        "services": services_dict,

        # ── 3. Telemetria ──
        "last_seen": time.time(),
    }
    registry.node_registry[request.id] = node_data

    if is_new:
        service_names = list(services_dict.keys())
        logging.info(
            f"Zarejestrowano Zjednoczony Węzeł: {request.id} "
            f"(host={request.host}:{request.port}, usługi={service_names})"
        )
        await event_bus.publish({
            "type": "node_registered",
            "id": request.id,
            "node": node_data,
        })

    return {
        "status": "registered",
        "id": request.id,
        "config": {
            "name": name,
            "services": services_dict,
        }
    }


@router_nodes.get("/v1/nodes/{node_id}/config")
async def get_node_config(node_id: str):
    """Zwraca profil konfiguracji Węzła przechowywany w Kontrolerze."""
    persistent_configs = load_nodes_config()
    if node_id in persistent_configs:
        return persistent_configs[node_id]
    if node_id in registry.node_registry:
        node = registry.node_registry[node_id]
        return {"name": node.get("name"), "services": node.get("services", {})}
    raise HTTPException(status_code=404, detail=f"Węzeł {node_id} nie został odnaleziony.")


@router_nodes.post("/v1/nodes/{node_id}/config")
async def update_node_config(node_id: str, body: ClientConfigRequest):
    """Zapisuje konfigurację Węzła w Kontrolerze i synchronizuje ją po sieci z Węzłem (port 8099)."""
    persistent_configs = load_nodes_config()
    current_profile = persistent_configs.get(node_id, {})

    new_name = body.name if body.name is not None else current_profile.get("name", node_id)
    new_services = body.services if body.services else current_profile.get("services", {})

    updated_profile = {
        "name": new_name,
        "services": new_services,
    }
    persistent_configs[node_id] = updated_profile
    save_nodes_config(persistent_configs)

    if node_id in registry.node_registry:
        success = await registry.node_manager.send_command(node_id, "config", updated_profile)
        if not success:
            # Revert the config if node is unreachable
            persistent_configs[node_id] = current_profile
            save_nodes_config(persistent_configs)
            logging.warning(f"Nie udało się wysłać konfiguracji przez WS do Węzła {node_id}. Zmiany wycofane.")
            raise HTTPException(status_code=502, detail=f"Węzeł {node_id} jest nieosiągalny (brak połączenia WebSocket). Nie można zaaplikować konfiguracji.")

        # Update in-memory registry only if network push was successful
        registry.node_registry[node_id]["name"] = new_name
        registry.node_registry[node_id]["services"] = new_services

    await event_bus.publish({
        "type": "node_updated",
        "id": node_id,
        "node": registry.node_registry.get(node_id, {"id": node_id, **updated_profile}),
    })

    return {"status": "ok", "config": updated_profile}


@router_nodes.delete("/v1/nodes/{node_id}")
async def unregister_node(node_id: str):
    """Wyrejestrowuje Zjednoczony Węzeł z Kontrolera."""
    if node_id in registry.node_registry:
        del registry.node_registry[node_id]
        logging.info(f"Wyrejestrowano Zjednoczony Węzeł: {node_id}")
        await event_bus.publish({"type": "node_unregistered", "id": node_id})
    return {"status": "ok"}

@router_nodes.websocket("/v1/ws/nodes/{node_id}")
async def websocket_node_endpoint(websocket: WebSocket, node_id: str):
    """Stałe połączenie WebSocket utrzymywane przez Węzeł."""
    await registry.node_manager.connect(node_id, websocket)
    
    # Automatyczny push konfiguracji zapamiętanej w Kontrolerze dla tego node_id
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
            if msg_type == "status":
                pass # Status jest trzymany po stronie węzła, heartbeat wystarczy
            elif msg_type == "satellite_event":
                try:
                    event = WSSatelliteEvent(**data)
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
                            await registry.node_manager.send_command(node_id, "service_control", {"action": "resume"})
                except Exception as e:
                    logging.error(f"Błąd parsowania WSSatelliteEvent: {e}")
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
                await registry.node_manager.send_command(node_id, "service_control", {"action": "resume"})
    except WebSocketDisconnect:
        registry.node_manager.disconnect(node_id)
        logging.info(f"Węzeł {node_id} rozłączył się (WebSocket).")

