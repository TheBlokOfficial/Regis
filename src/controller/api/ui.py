"""
Router Web UI dla Kontrolera.

Obsługuje trzy endpointy:
- GET  /api/events              — SSE: strumień zdarzeń z EventBus
- GET  /api/status              — REST: snapshot stanu systemu
- POST /api/node/{node_id}/command — proxy komendy do węzła Windows
"""
import asyncio
import json
import logging
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import controller.core.event_bus as event_bus
import controller.core.client_registry as registry

router_ui = APIRouter()


# ---------------------------------------------------------------------------
# Modele danych
# ---------------------------------------------------------------------------

class NodeCommand(BaseModel):
    command: str  # np. service_control, status, config
    data: dict = {}

class SatelliteEvent(BaseModel):
    satellite_id: str
    type: str   # state | stt_result | done | error
    data: dict = {}


# (Usunięto stare mapowanie _COMMAND_MAP HTTP, używamy tylko WebSocket z dowolnym JSON)


# ---------------------------------------------------------------------------
# Endpoint: SSE stream zdarzeń
# ---------------------------------------------------------------------------

@router_ui.get("/api/events")
async def events_stream(request: Request):
    """Strumieniuje zdarzenia systemu do przeglądarki przez SSE.

    Nowy klient dostaje najpierw pełną historię ostatnich eventów,
    następnie na bieżąco nowe zdarzenia.
    Heartbeat co 15s utrzymuje połączenie przy bezczynności.
    """
    async def generator():
        q, history = await event_bus.subscribe()
        try:
            # Odtwórz historię dla nowego klienta
            for event in history:
                event_copy = dict(event)
                event_copy["is_history"] = True
                yield f"data: {json.dumps(event_copy)}\n\n"

            # Strumieniuj nowe zdarzenia
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            event_bus.unsubscribe(q)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


# ---------------------------------------------------------------------------
# Endpoint: snapshot stanu systemu
# ---------------------------------------------------------------------------

@router_ui.get("/api/status")
async def get_status():
    """Zwraca aktualny stan systemu: węzły, satelity, integracje, info o Kontrolerze."""
    uptime_s = int(time.time() - registry.controller_start_time)

    # Pobieranie statusów wszystkich zarejestrowanych integracji
    integrations = []
    for integration in registry.integration_registry.values():
        try:
            status = await integration.check_status()
        except Exception:
            status = "offline"
        integrations.append(integration.to_dict(status))

    # Wyciągnięcie ha_status dla wstecznej kompatybilności
    ha_integration = registry.integration_registry.get("home_assistant")
    ha_status = integrations[0]["status"] if ha_integration and integrations else "unknown"

    nodes = list(registry.node_registry.values())
    workers = registry.get_worker_nodes()
    satellites = registry.get_satellite_nodes()

    return {
        "nodes": nodes,
        "workers": workers,
        "satellites": satellites,
        "integrations": integrations,
        "controller": {
            "uptime_s": uptime_s,
            "ha_status": ha_status,
        }
    }


# ---------------------------------------------------------------------------
# Endpoint: proxy komendy do węzła
# ---------------------------------------------------------------------------

@router_ui.post("/api/node/{node_id}/command")
async def node_command(node_id: str, body: NodeCommand):
    """Przekazuje komendę do węzła Windows przez WebSocket."""
    command = body.command
    payload = body.data

    # Szukamy węzła w rejestrze Zjednoczonych Węzłów lub workerów
    node = registry.node_registry.get(node_id) or registry.worker_registry.get(node_id)
    if not node:
        return JSONResponse(
            {"error": f"Węzeł '{node_id}' nie jest zarejestrowany."},
            status_code=404
        )

    success = await registry.node_manager.send_command(node_id, command, payload)
    if not success:
        error_msg = f"Węzeł {node_id} jest nieosiągalny (brak aktywnego połączenia WebSocket)."
        logging.warning(f"[UI] Komenda '{command}' do węzła '{node_id}' nie powiodła się: {error_msg}")
        await event_bus.publish({
            "type": "node_command_result",
            "node_id": node_id,
            "command": command,
            "success": False,
            "error": error_msg,
        })
        return JSONResponse({"error": error_msg}, status_code=502)

    # Sukces wysłania komendy - odpowiedź przyjdzie przez WebSocket jako `command_result`
    logging.info(f"[UI] Komenda '{command}' wysłana do węzła '{node_id}' przez WS.")
    return {"status": "pending", "node_id": node_id, "command": command}


# ---------------------------------------------------------------------------
# Endpoint: zdarzenia Satelity → EventBus Kontrolera
# ---------------------------------------------------------------------------

@router_ui.post("/api/satellite/event")
async def satellite_event(body: SatelliteEvent):
    """Odbiera zdarzenie od Satelity (VAD, WakeWord, zmiana stanu)
    i publikuje je na centralnym EventBus Kontrolera.

    Dzięki temu zdarzenia audio pojawiają się w czasie rzeczywistym
    w Web UI bez odpytywania węzła.
    """
    if body.satellite_id in registry.satellite_registry:
        registry.satellite_registry[body.satellite_id]["last_seen"] = time.time()

    await event_bus.publish({
        "type": "satellite_event",
        "satellite_id": body.satellite_id,
        "event_type": body.type,
        "data": body.data,
    })
    return {"status": "ok"}
