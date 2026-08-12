from fastapi import FastAPI
import shared
from shared import EventBus
from server.core.engine import AgentEngine
from server.network.satellite_ws import register_satellite_websocket


def create_gateway_app(agent_engine: AgentEngine, event_bus: EventBus) -> FastAPI:
    """Tworzy i konfiguruje bramkę sieciową FastAPI dla komunikacji z satelitami."""
    app = FastAPI(
        title="Regis Agent OS - Satellite Gateway",
        description="Adapter sieciowy komunikacji z satelitami (mikrofon/głośnik)",
        version="0.1.0",
    )

    @app.get("/")
    async def root():
        return {
            "system": "Regis Agent OS",
            "gateway_status": "online",
            "agent_engine_running": agent_engine.is_running,
            "shared_version": shared.__version__,
        }

    # Rejestrujemy punkty końcowe WebSockets dla satelitów, przekazując magistralę zdarzeń
    register_satellite_websocket(app_router=app.router, event_bus=event_bus)

    return app
