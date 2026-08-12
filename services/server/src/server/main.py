import asyncio
import uvicorn
from shared import EventBus, get_logger, setup_logging

from server.agent import AgentEngine
from server.agent.backend import BackendRegistry
from server.config import load_settings
from server.network.gateway import create_gateway_app

# 1. Konfiguracja jednolitych, minimalistycznych logów
setup_logging(level="INFO")
logger = get_logger("regis.main")


async def main() -> None:
    settings = load_settings()
    logger.info(f"Uruchamianie {settings.app_name} (v{settings.version})...")

    # 1. Tworzenie centralnej magistrali zdarzeń (Event Bus)
    event_bus = EventBus()

    # 2. Inicjalizacja rejestru backendów i pobranie aktywnego dostawcy LLM
    backend_registry = BackendRegistry()
    active_llm_provider = await backend_registry.get_active_provider()

    # 3. Inicjalizacja rdzenia Agenta z aktywnym dostawcą LLM
    agent_engine = AgentEngine(llm_provider=active_llm_provider)
    await agent_engine.initialize()

    # 4. Inicjalizacja bramki sieciowej z podpiętą magistralą zdarzeń i rejestrem backendów
    app = create_gateway_app(
        agent_engine=agent_engine,
        event_bus=event_bus,
        backend_registry=backend_registry,
    )

    # 5. Start serwera uvicorn
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
