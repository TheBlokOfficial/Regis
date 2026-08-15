import asyncio
import uvicorn
from shared import EventBus, get_logger, setup_logging

from server.agent import AgentEngine
from server.agent.backend import BackendRegistry
from server.agent.context import ContextBuilder
from server.agent.gateway import Gateway
from server.agent.prompts import PromptStore
from server.plugins.datetime_plugin import DateTimePlugin
from server.plugins.smart_home import SmartHomePlugin
from server.config import load_settings
from server.integrations import home_assistant as ha_integration
from server.network.gateway import create_gateway_app

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

    # 4. Inicjalizacja pluginu Smart Home (Warstwa 1) — Gateway go nie zna z góry, wpinamy go
    #    tutaj, w kompozycji aplikacji, jako jeden z (dziś jedynych) zarejestrowanych PluginProvider.
    #    Plugin z kolei nie zna żadnej konkretnej integracji na sztywno — każda integracja
    #    (Warstwa 2) rejestruje się w nim jawnie, tutaj, w kompozycji aplikacji.
    smart_home_plugin = SmartHomePlugin()
    smart_home_plugin.register_integration_type(
        ha_integration.TYPE_NAME, ha_integration.create, ha_integration.SCHEMA
    )
    datetime_plugin = DateTimePlugin()

    # 5. Inicjalizacja Gateway — jedyny agregator Warstwy 0, spinający Pluginy w trzy
    #    płaskie kanały treści agenta (narzędzia, encje, fakty).
    gateway = Gateway(plugins=[smart_home_plugin, datetime_plugin])

    # 6. Inicjalizacja rdzenia Agenta z aktywnym dostawcą LLM, EventBus, skonfigurowanym limitem historii, PromptStore i Gateway
    context_builder = ContextBuilder(max_history_messages=settings.max_history_messages)
    agent_engine = AgentEngine(
        llm_provider=active_llm_provider,
        context_builder=context_builder,
        event_bus=event_bus,
        prompt_store=prompt_store,
        gateway=gateway,
        max_tool_iterations=settings.max_tool_iterations,
    )
    await agent_engine.initialize()

    # 7. Inicjalizacja bramki sieciowej z rejestrem backendów, magazynem promptów i tym samym
    #    pluginem Smart Home (współdzielona instancja — konfiguracja przez REST jest od razu widoczna dla agenta)
    app = create_gateway_app(
        agent_engine=agent_engine,
        backend_registry=backend_registry,
        prompt_store=prompt_store,
        smart_home_plugin=smart_home_plugin,
    )

    # 8. Start serwera uvicorn
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
