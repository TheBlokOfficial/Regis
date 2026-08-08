"""
Router Systemowy (UI / Events / Status) dla Kontrolera.

Obsługuje endpointy:
- GET  /api/events              — SSE: strumień zdarzeń z EventBus
- GET  /api/status              — REST: snapshot stanu systemu
- POST /api/node/{node_id}/command — proxy komendy do klienta
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

router_system = APIRouter()


# ---------------------------------------------------------------------------
# Endpoint: snapshot stanu systemu
# ---------------------------------------------------------------------------

@router_system.get("/api/status")
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

    clients = list(client_store.client_registry.values())
    workers = client_store.get_llm_clients()
    satellites = client_store.get_satellite_clients()

    return {
        "nodes": clients,  # Klucze zachowane dla kompatybilności z UI
        "clients": clients,
        "workers": workers,
        "satellites": satellites,
        "integrations": integrations,
        "controller": {
            "uptime_s": uptime_s,
            "ha_status": ha_status,
        }
    }
