from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server.agent import AgentEngine
from server.agent.backend import BackendRegistry
from server.agent.prompts import PromptStore
from server.network.routes import create_api_router
from server.world import WorldEngine
from server.world.routes import create_world_router


def create_gateway_app(
    agent_engine: AgentEngine,
    backend_registry: BackendRegistry,
    prompt_store: PromptStore,
    world_engine: WorldEngine | None = None,
) -> FastAPI:
    """Tworzy i konfiguruje bramkę sieciową FastAPI z wbudowaną konsolą WWW i punktami końcowymi."""
    app = FastAPI(
        title="Regis Agent OS - Gateway",
        description="Bramka sieciowa FastAPI z wbudowanym interfejsem Web Console",
        version="0.1.0",
    )

    # Rejestracja centralnego routera używanych punktów końcowych API
    api_router = create_api_router(
        agent_engine=agent_engine,
        backend_registry=backend_registry,
        prompt_store=prompt_store,
    )
    app.include_router(api_router)

    # WorldEngine jest jedynym, konkretnym silnikiem świata — sieć montuje jego
    # router wprost, pod stałym prefiksem, bez generycznej pętli po rozszerzeniach.
    # Opcjonalny — testy chat API, którym konfiguracja świata jest obojętna, mogą
    # pominąć wstrzyknięcie i dostać czysty kernel bez zamontowanego routera.
    if world_engine is not None:
        app.include_router(create_world_router(world_engine), prefix="/api/v1/world")

    # Wbudowana obsługa interfejsu Web Console (server/web)
    web_dir = (Path(__file__).parent.parent / "web").resolve()
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
