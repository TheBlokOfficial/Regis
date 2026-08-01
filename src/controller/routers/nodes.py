import logging
import time
from fastapi import APIRouter

from core.schemas import NodeRegistrationRequest
import controller.event_bus as event_bus
import controller.registry as registry

router_nodes = APIRouter()


@router_nodes.post("/v1/nodes/register")
async def register_node(request: NodeRegistrationRequest):
    """Rejestruje Zjednoczony Węzeł w Kontrolerze."""
    node_data = {
        "id": request.id,
        "name": request.name or request.id,
        "host": request.host,
        "port": request.port,
        "services": request.services,
        "model_name": request.model_name,
        "priority": request.priority,
        "room": request.room,
        "node_type": request.node_type,
        "capabilities": request.capabilities,
        "wakeword_local": request.wakeword_local,
        "last_seen": time.time(),
    }
    registry.node_registry[request.id] = node_data
    logging.info(f"Zarejestrowano Zjednoczony Węzeł: {request.id} (host={request.host}:{request.port}, usługi={request.services})")
    
    await event_bus.publish({
        "type": "node_registered",
        "id": request.id,
        "node": node_data,
    })
    return {"status": "registered", "id": request.id}


@router_nodes.delete("/v1/nodes/{node_id}")
async def unregister_node(node_id: str):
    """Wyrejestrowuje Zjednoczony Węzeł z Kontrolera."""
    if node_id in registry.node_registry:
        del registry.node_registry[node_id]
        logging.info(f"Wyrejestrowano Zjednoczony Węzeł: {node_id}")
        await event_bus.publish({"type": "node_unregistered", "id": node_id})
    return {"status": "ok"}
