from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import shared
from shared import EventBus
from server.agent import AgentEngine
from server.network.satellite_ws import register_satellite_websocket


def create_gateway_app(agent_engine: AgentEngine, event_bus: EventBus) -> FastAPI:
    """Tworzy i konfiguruje bramkę sieciową FastAPI z wbudowaną konsolą WWW i punktami końcowymi."""
    app = FastAPI(
        title="Regis Agent OS - Gateway",
        description="Bramka sieciowa FastAPI z wbudowanym interfejsem Web Console oraz WebSockets",
        version="0.1.0",
    )

    @app.get("/api/health")
    async def health():
        return {
            "system": "Regis Agent OS",
            "gateway_status": "online",
            "agent_engine_status": "ready",
            "shared_version": shared.__version__,
        }

    # Rejestracja punktów końcowych WebSockets dla Satelitów
    register_satellite_websocket(app_router=app.router, event_bus=event_bus)

    # Wbudowana obsługa interfejsu Web Console (server/web)
    web_dir = (Path(__file__).parent.parent / "web").resolve()
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
