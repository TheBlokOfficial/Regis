from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from server.agent import AgentEngine
from server.agent.backend import BackendRegistry
from server.agent.prompts import PromptStore
from server.network.extension_contract import NetworkExtension
from server.network.routes import create_api_router
from server.network.routes.extensions import create_extensions_registry_router


def create_gateway_app(
    agent_engine: AgentEngine,
    backend_registry: BackendRegistry,
    prompt_store: PromptStore,
    extensions: list[NetworkExtension] | None = None,
) -> FastAPI:
    """Tworzy i konfiguruje bramkę sieciową FastAPI z wbudowaną konsolą WWW i punktami końcowymi."""
    app = FastAPI(
        title="Regis Agent OS - Gateway",
        description="Bramka sieciowa FastAPI z wbudowanym interfejsem Web Console",
        version="0.1.0",
    )
    extensions = extensions or []

    # Rejestracja centralnego routera używanych punktów końcowych API
    api_router = create_api_router(
        agent_engine=agent_engine,
        backend_registry=backend_registry,
        prompt_store=prompt_store,
    )
    app.include_router(api_router)

    # Generyczny rejestr rozszerzeń (lista + przełącznik enabled), plus router
    # własny każdego rozszerzenia zamontowany pod jego prefiksem — sieć zna
    # wyłącznie kształt `NetworkExtension`, nigdy konkretnej implementacji.
    app.include_router(create_extensions_registry_router(extensions))
    for ext in extensions:
        app.include_router(ext.build_router(), prefix=f"/api/v1/extensions/{ext.extension_id}")

    # Wbudowana obsługa interfejsu Web Console (server/web)
    web_dir = (Path(__file__).parent.parent / "web").resolve()
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app
