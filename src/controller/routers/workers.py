import logging
from fastapi import APIRouter

from core.schemas import WorkerRegistrationRequest
import controller.event_bus as event_bus
import controller.registry as registry

router_workers = APIRouter()


@router_workers.post("/v1/workers/register")
async def register_worker(request: WorkerRegistrationRequest):
    """Rejestruje Węzeł Roboczy w Kontrolerze. Wywoływane przez Worker przy starcie."""
    is_new = request.id not in registry.worker_registry
    registry.worker_registry[request.id] = {
        "id": request.id,
        "host": request.host,
        "port": request.port,
        "model_name": request.model_name,
        "priority": request.priority,
        "base_url": f"http://{request.host}:{request.port}"
    }
    if is_new:
        logging.info(f"Zarejestrowano węzeł: {request.id} @ {request.host}:{request.port} (priority={request.priority})")
        await event_bus.publish({
            "type": "worker_registered",
            "id": request.id,
            "host": request.host,
            "port": request.port,
            "model_name": request.model_name,
            "priority": request.priority,
        })
    return {"status": "registered", "id": request.id}


@router_workers.delete("/v1/workers/{worker_id}")
async def unregister_worker(worker_id: str):
    """Wyrejestrowuje Węzeł Roboczy. Wywoływane przez Worker przy zamknięciu."""
    if worker_id in registry.worker_registry:
        del registry.worker_registry[worker_id]
        logging.info(f"Wyrejestrowano węzeł: {worker_id}")
        await event_bus.publish({"type": "worker_unregistered", "id": worker_id})
    return {"status": "ok"}


@router_workers.get("/v1/workers")
async def list_workers():
    """Zwraca listę aktywnych węzłów roboczych (diagnostyka)."""
    return {"workers": list(registry.worker_registry.values())}
