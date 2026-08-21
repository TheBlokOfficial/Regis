from pathlib import Path
from fastapi import APIRouter, FastAPI
from fastapi.staticfiles import StaticFiles
from server.agent import AgentEngine
from server.ai.llm import BackendRegistry
from server.agent.prompts import AgentDefaultPromptStore
from server.network.routes import create_api_router
from server.world import WorldEngine
from server.world.routes import create_world_router


def create_gateway_app(
    agent_engine: AgentEngine,
    backend_registry: BackendRegistry,
    prompt_store: AgentDefaultPromptStore,
    world_engine: WorldEngine | None = None,
    voice_router: APIRouter | None = None,
    voice_status_router: APIRouter | None = None,
    voice_providers_router: APIRouter | None = None,
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

    # `server.voice` (WS gateway satelit) jest opcjonalny i całkowicie rozłączny z
    # `server.world` — zna wyłącznie AgentEngine, montowany osobno pod stałym
    # prefiksem, bez pośredniego protokołu ani wiedzy o World.
    if voice_router is not None:
        app.include_router(voice_router, prefix="/ws")
    if voice_status_router is not None:
        app.include_router(voice_status_router, prefix="/api/v1/voice")
    if voice_providers_router is not None:
        app.include_router(voice_providers_router, prefix="/api/v1/voice")

    # Wbudowana obsługa interfejsu Web Console (server/web)
    web_dir = (Path(__file__).parent.parent / "web").resolve()
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    @app.middleware("http")
    async def _no_cache_static_assets(request, call_next):
        """SPA bez wersjonowanych nazw plików (`app.js`, nie `app.abc123.js`) — bez tego
        nagłówka przeglądarki potrafią heurystycznie cache'ować JS/CSS na długo (brak
        `Cache-Control` w domyślnym `StaticFiles`), więc zmiana kodu po wdrożeniu może nie
        być widoczna bez twardego odświeżenia. `no-cache` wymusza tanią rewalidację
        (warunkowe GET po ETag/Last-Modified) przy każdym żądaniu, nigdy cichą stałość."""
        response = await call_next(request)
        if request.url.path.startswith(("/js/", "/css/")):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app
