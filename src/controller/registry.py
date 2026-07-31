import asyncio
import logging
import requests
from fastapi import APIRouter

from core.schemas import WorkerRegistrationRequest, SatelliteRegistrationRequest
from integrations.ha_client import HomeAssistantClient
from core.tools_registry import ToolsRegistry

# ─── Globalne instancje — inicjalizowane w lifespan ───────────────────────
ha_client: HomeAssistantClient | None = None
tools_registry: ToolsRegistry | None = None
worker_registry: dict[str, dict] = {}
satellite_registry: dict[str, dict] = {}
_settings_cache: dict = {}
conversation_history: list[dict] = []
last_interaction_time: float = 0.0

# ─── Priorytety tierów usunięto zgodnie z Phase 1 ────────────────────────

router_workers = APIRouter()
router_satellites = APIRouter()


async def _heartbeat_loop():
    """W tle sprawdza dostępność węzłów, usuwa martwe i czyści historię po 60s bezczynności."""
    import time
    global last_interaction_time
    
    while True:
        await asyncio.sleep(30)
        
        # 1. Automatyczne czyszczenie pamięci
        if conversation_history and (time.time() - last_interaction_time > 60.0):
            logging.info("Brak interakcji przez 60 sekund. Automatyczne czyszczenie pamięci (historii).")
            conversation_history.clear()
            
        # 2. Sprawdzanie zdrowia węzłów
        workers = list(worker_registry.values())
        for w in workers:
            try:
                url = f"{w['base_url']}/v1/health"
                resp = await asyncio.to_thread(requests.get, url, timeout=1.0)
                resp.raise_for_status()
            except Exception as e:
                logging.warning(f"[Heartbeat] Węzeł {w['id']} nie odpowiada ({type(e).__name__}). Usuwam z rejestru.")
                if w['id'] in worker_registry:
                    del worker_registry[w['id']]



# ─────────────────────────────────────────────────────────────────────────────
#  Rejestr Węzłów Roboczych
# ─────────────────────────────────────────────────────────────────────────────

@router_workers.post("/v1/workers/register")
async def register_worker(request: WorkerRegistrationRequest):
    """Rejestruje Węzeł Roboczy w Kontrolerze. Wywoływane przez Worker przy starcie."""
    worker_registry[request.id] = {
        "id": request.id,
        "host": request.host,
        "port": request.port,
        "model_name": request.model_name,
        "tier": request.tier,
        "base_url": f"http://{request.host}:{request.port}"
    }
    logging.info(f"Zarejestrowano węzeł: {request.id} @ {request.host}:{request.port} (tier={request.tier})")
    return {"status": "registered", "id": request.id}


@router_workers.delete("/v1/workers/{worker_id}")
async def unregister_worker(worker_id: str):
    """Wyrejestrowuje Węzeł Roboczy. Wywoływane przez Worker przy zamknięciu."""
    if worker_id in worker_registry:
        del worker_registry[worker_id]
        logging.info(f"Wyrejestrowano węzeł: {worker_id}")
    return {"status": "ok"}


@router_workers.get("/v1/workers")
async def list_workers():
    """Zwraca listę aktywnych węzłów roboczych (diagnostyka)."""
    return {"workers": list(worker_registry.values())}


# ───────────────────────────────────────────────────────────────────────────────
#  Rejestr Satelit
# ───────────────────────────────────────────────────────────────────────────────

@router_satellites.post("/v1/satellites/register")
async def register_satellite(request: SatelliteRegistrationRequest):
    """Rejestruje Satelitę w Kontrolerze. Wywoływane przez Satelitę przy starcie."""
    satellite_registry[request.id] = {
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
    if satellite_id in satellite_registry:
        del satellite_registry[satellite_id]
        logging.info(f"Wyrejestrowano satelitę: {satellite_id}")
    return {"status": "ok"}
