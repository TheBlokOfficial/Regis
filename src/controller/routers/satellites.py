import logging
from fastapi import APIRouter

from core.schemas import SatelliteRegistrationRequest
import controller.registry as registry

router_satellites = APIRouter()


@router_satellites.post("/v1/satellites/register")
async def register_satellite(request: SatelliteRegistrationRequest):
    """Rejestruje Satelitę w Kontrolerze. Wywoływane przez Satelitę przy starcie."""
    registry.satellite_registry[request.id] = {
        "id": request.id,
        "room": request.room,
        "type": request.type,
        "capabilities": request.capabilities,
        "wakeword_local": request.wakeword_local,
    }
    logging.info(f"Zarejestrowano satelitę: {request.id} (pokój={request.room}, typ={request.type})")
    return {"status": "registered", "id": request.id}


@router_satellites.delete("/v1/satellites/{satellite_id}")
async def unregister_satellite(satellite_id: str):
    """Wyrejestrowuje Satelitę. Wywoływane przez Satelitę przy zamknięciu."""
    if satellite_id in registry.satellite_registry:
        del registry.satellite_registry[satellite_id]
        logging.info(f"Wyrejestrowano satelitę: {satellite_id}")
    return {"status": "ok"}
