from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from shared import EventBus
from server.agent import AgentEngine
from server.agent.backend import BackendRegistry
from server.network.routes import create_api_router


def create_gateway_app(
    agent_engine: AgentEngine,
    event_bus: EventBus,
    backend_registry: BackendRegistry,
) -> FastAPI:
    """Tworzy i konfiguruje bramkę sieciową FastAPI z wbudowaną konsolą WWW i punktami końcowymi."""
    app = FastAPI(
        title="Regis Agent OS - Gateway",
        description="Bramka sieciowa FastAPI z wbudowanym interfejsem Web Console",
        version="0.1.0",
    )

    # Rejestracja centralnego routera używanych punktów końcowych API
    api_router = create_api_router(agent_engine=agent_engine, backend_registry=backend_registry)
    app.include_router(api_router)

    # Wbudowana obsługa interfejsu Web Console (server/web)
    web_dir = (Path(__file__).parent.parent / "web").resolve()
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
