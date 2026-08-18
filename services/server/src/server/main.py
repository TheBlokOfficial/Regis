import asyncio
import uvicorn
from shared import EventBus, get_logger, setup_logging

from server.agent import AgentEngine
from server.agent.backend import BackendRegistry
from server.agent.context import ContextBuilder
from server.agent.prompts import PromptStore
from server.config import load_settings
from server.network.gateway import create_gateway_app
from server.world import WorldEngine

# 1. Konfiguracja jednolitych, minimalistycznych logów
setup_logging(level="INFO")
logger = get_logger("regis.main")


async def main() -> None:
    settings = load_settings()
    logger.info(f"Uruchamianie {settings.app_name} (v{settings.version})...")

    # 1. Tworzenie centralnej magistrali zdarzeń (Event Bus), współdzielonej przez AgentEngine
    event_bus = EventBus()

    # 2. Inicjalizacja rejestru backendów i pobranie aktywnego dostawcy LLM
    backend_registry = BackendRegistry()
    active_llm_provider = await backend_registry.get_active_provider()

    # 3. Inicjalizacja magazynu promptów systemowych i upewnienie się, że domyślny prompt istnieje
    prompt_store = PromptStore()
    await prompt_store.ensure_defaults()

    # 4. Inicjalizacja jedynego, konkretnego silnika świata — kernel go nie zna z góry,
    #    zna wyłącznie kształt `WorldInterface` (agent/context_provider.py). Wstrzykiwany
    #    tutaj, w kompozycji aplikacji, dokładnie jak dostawca LLM czy PromptStore.
    world_engine = WorldEngine()

    # 5. Inicjalizacja rdzenia Agenta z aktywnym dostawcą LLM, EventBus, skonfigurowanym limitem historii, PromptStore i WorldEngine
    context_builder = ContextBuilder(max_history_messages=settings.max_history_messages)
    agent_engine = AgentEngine(
        llm_provider=active_llm_provider,
        context_builder=context_builder,
        event_bus=event_bus,
        prompt_store=prompt_store,
        world=world_engine,
        max_tool_iterations=settings.max_tool_iterations,
    )
    await agent_engine.initialize()

    # 6. Inicjalizacja bramki sieciowej z rejestrem backendów, magazynem promptów i tą samą
    #    instancją WorldEngine — konfiguracja przez REST jest od razu widoczna dla agenta,
    #    bo `WorldEngine.build()` czyta stan na bieżąco, co turę.
    app = create_gateway_app(
        agent_engine=agent_engine,
        backend_registry=backend_registry,
        prompt_store=prompt_store,
        world_engine=world_engine,
    )

    # 7. Start serwera uvicorn
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
    )

    server = uvicorn.Server(config)

    logger.info(f"Bramka sieciowa gotowa na http://{settings.host}:{settings.port}")
    try:
        await server.serve()
    finally:
        await agent_engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
