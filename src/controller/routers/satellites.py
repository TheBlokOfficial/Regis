import time
from fastapi import APIRouter

from core.schemas import SatelliteRegistrationRequest
import controller.event_bus as event_bus
import controller.registry as registry

router_satellites = APIRouter()


@router_satellites.post("/v1/satellites/register")
async def register_satellite(request: SatelliteRegistrationRequest):
    """Rejestruje Satelitę w Kontrolerze. Wywoływane przez Satelitę przy starcie."""
    is_new = request.id not in registry.satellite_registry
    registry.satellite_registry[request.id] = {
        "id": request.id,
        "room": request.room,
        "type": request.type,
        "capabilities": request.capabilities,
        "wakeword_local": request.wakeword_local,
        "last_seen": time.time(),
    }
    logging.info(f"Zarejestrowano satelitę: {request.id} (pokój={request.room}, typ={request.type})")
    if is_new:
        await event_bus.publish({
            "type": "satellite_registered",
            "id": request.id,
            "room": request.room,
            "type": request.type,
            "capabilities": request.capabilities,
        })
    return {"status": "registered", "id": request.id}


@router_satellites.delete("/v1/satellites/{satellite_id}")
async def unregister_satellite(satellite_id: str):
    """Wyrejestrowuje Satelitę. Wywoływane przez Satelitę przy zamknięciu."""
    if satellite_id in registry.satellite_registry:
        del registry.satellite_registry[satellite_id]
        logging.info(f"Wyrejestrowano satelitę: {satellite_id}")
        await event_bus.publish({"type": "satellite_unregistered", "id": satellite_id})
    return {"status": "ok"}
