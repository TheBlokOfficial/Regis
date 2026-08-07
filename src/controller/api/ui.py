"""
Router Web UI dla Kontrolera.

Obsługuje cztery endpointy:
- GET  /api/events              — SSE: strumień zdarzeń z EventBus
- GET  /api/status              — REST: snapshot stanu systemu
- POST /api/node/{node_id}/command — proxy komendy do węzła Windows
- POST /api/satellite/event     — zdarzenia Satelity → EventBus
"""
import asyncio
import json
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

import controller.core.event_bus as event_bus
import controller.core.app_state as app_state
import controller.core.client_store as client_store
from controller.core.connection_manager import client_manager

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
    uptime_s = int(time.time() - app_state.controller_start_time)

    # Pobieranie statusów wszystkich zarejestrowanych integracji
    integrations = []
    for integration in app_state.integration_registry.values():
        try:
            status = await integration.check_status()
        except Exception:
            status = "offline"
        integrations.append(integration.to_dict(status))

    # Wyciągnięcie ha_status dla wstecznej kompatybilności
    ha_integration = app_state.integration_registry.get("home_assistant")
    ha_status = integrations[0]["status"] if ha_integration and integrations else "unknown"

    nodes = list(client_store.client_registry.values())
    workers = client_store.get_llm_clients()
    satellites = client_store.get_satellite_clients()

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

    node = client_store.client_registry.get(node_id)
    if not node:
        return JSONResponse(
            {"error": f"Węzeł '{node_id}' nie jest zarejestrowany."},
            status_code=404
        )

    success = await client_manager.send_command(node_id, command, payload)
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

    logging.info(f"[UI] Komenda '{command}' wysłana do węzła '{node_id}' przez WS.")
    return {"status": "pending", "node_id": node_id, "command": command}


# ---------------------------------------------------------------------------
# Endpoint: zdarzenia Satelity → EventBus Kontrolera
# ---------------------------------------------------------------------------

@router_ui.post("/api/satellite/event")
async def satellite_event(body: SatelliteEvent):
    """Odbiera zdarzenie od Satelity (VAD, WakeWord, zmiana stanu)
    i publikuje je na centralnym EventBus Kontrolera.
    """
    if body.satellite_id in client_store.client_registry:
        client_store.client_registry[body.satellite_id]["last_seen"] = time.time()

    await event_bus.publish({
        "type": "satellite_event",
        "satellite_id": body.satellite_id,
        "event_type": body.type,
        "data": body.data,
    })
    return {"status": "ok"}
