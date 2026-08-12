import asyncio
import uvicorn
from shared import EventBus, get_logger, setup_logging

from server.core.engine import AgentEngine
from server.network.gateway import create_gateway_app

# 1. Konfiguracja jednolitych, minimalistycznych logów
setup_logging(level="INFO")
logger = get_logger("regis.main")


async def main() -> None:
    logger.info("Uruchamianie Systemu Operacyjnego Agenta AI (Regis OS)...")

    # 2. Tworzenie centralnej magistrali zdarzeń (Event Bus)
    event_bus = EventBus()

    # 3. Inicjalizacja rdzenia Agenta z podpiętą magistralą zdarzeń
    agent_engine = AgentEngine(event_bus=event_bus)
    await agent_engine.initialize()

    # 4. Inicjalizacja bramki sieciowej dla satelitów z podpiętą magistralą zdarzeń
    app = create_gateway_app(agent_engine=agent_engine, event_bus=event_bus)

    # 5. Start serwera uvicorn (port 8000, log_config=None zachowuje nasz format)
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )

    server = uvicorn.Server(config)

    logger.info("Bramka sieciowa gotowa na http://0.0.0.0:8000 oraz ws://0.0.0.0:8000/ws/satellite/{id}")
    try:
        await server.serve()
    finally:
        await agent_engine.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
