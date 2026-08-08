"""
Router Systemowy (Status) dla Kontrolera.

Obsługuje endpointy:
- GET  /api/status              — REST: snapshot stanu systemu
- GET  /api/events              — SSE: strumieniowanie zdarzeń EventBus
"""
import time
import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

import controller.core.state as state
import controller.core.client_registry as client_registry
import controller.core.event_bus as event_bus

router_system = APIRouter()


async def get_status_snapshot() -> dict:
    """Zwraca aktualny stan systemu: węzły, satelity, integracje, info o Kontrolerze."""
    uptime_s = int(time.time() - state.controller_start_time)

    integrations = []
    for integration in state.integration_registry.values():
        try:
            status = await integration.check_status()
        except Exception:
            status = "offline"
        integrations.append(integration.to_dict(status))

    ha_integration = state.integration_registry.get("home_assistant")
    ha_status = integrations[0]["status"] if ha_integration and integrations else "unknown"

    clients = list(client_registry.client_registry.values())
    workers = client_registry.get_llm_clients()
    satellites = client_registry.get_satellite_clients()

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


@router_system.get("/api/status")
async def get_status():
    """Zwraca aktualny stan systemu: węzły, satelity, integracje, info o Kontrolerze."""
    return await get_status_snapshot()


@router_system.get("/api/events")
async def get_events(request: Request):
    """
    Endpoint SSE (Server-Sent Events) dla zdarzeń systemowych (EventBus).
    Zwraca historyczne zdarzenia od razu po podłączeniu, a następnie strumieniuje na żywo.
    """
    queue, history = await event_bus.subscribe()

    async def event_generator():
        try:
            for past_event in history:
                yield f"data: {json.dumps(past_event)}\n\n"
            
            while True:
                if await request.is_disconnected():
                    break
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            event_bus.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
