import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from controller import registry
from controller.routers.satellites import router_satellites
from controller.routers.workers import router_workers
from controller.routers.chat import router_chat
from controller.routers.tools import router_tools
from controller.routers.ui import router_ui
from core import config
from core.discovery import get_local_ip, start_discovery_server
from core.logger import setup_logging
from controller.tools_registry import ToolsRegistry
from controller.integrations.ha_client import HomeAssistantClient

# 1. Konfiguracja logowania zaraz po importach
setup_logging("controller")

# 2. Stałe konfiguracyjne
DEFAULT_CONTROLLER_PORT = 8000
DEFAULT_HA_URL = "http://192.168.0.50:8123"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uruchamia i zatrzymuje kluczowe usługi Kontrolera."""
    # Ładowanie konfiguracji
    settings = config.load_settings()
    aliases = config.load_aliases()
    virtual_groups = config.load_virtual_groups()
    rooms = config.load_rooms()

    # Inicjalizacja klienta Home Assistant
    registry.ha_client = HomeAssistantClient(
        url=settings.get("ha_url", DEFAULT_HA_URL),
        token=settings.get("ha_token", "TWÓJ_TOKEN_TUTAJ"),
        aliases=aliases,
        virtual_groups=virtual_groups,
    )

    # Rejestracja integracji Home Assistant w rejestrze
    from controller.integrations.ha_integration import HomeAssistantIntegration
    ha_integration = HomeAssistantIntegration(registry.ha_client)
    registry.register_integration(ha_integration)

    # Inicjalizacja rejestru narzędzi AI
    registry.tools_registry = ToolsRegistry(
        registry.ha_client, rooms=rooms
    )
    registry._settings_cache.update(settings)

    # Uruchomienie uslug w tle i Auto-Discovery
    heartbeat_task = asyncio.create_task(registry._heartbeat_loop())

    local_ip = get_local_ip()
    discovery_url = f"http://{local_ip}:{DEFAULT_CONTROLLER_PORT}"
    start_discovery_server(discovery_url)

    logging.info("Regis Controller uruchomiony.")

    yield  # Aplikacja działa i obsługuje zapytania

    # Zamknięcie usług przy wyłączaniu serwera
    heartbeat_task.cancel()
    logging.info("Regis Controller zatrzymany.")


# 3. Tworzenie aplikacji i wpinanie routerów
app = FastAPI(title="Regis Controller", lifespan=lifespan)

# Uwaga: router_ui MUSI być przed app.mount StaticFiles.
# StaticFiles jest catch-all i prześlonĪ endpointy /api/* jeśli dodane wcześniej.
routers = [
    router_workers,
    router_satellites,
    router_tools,
    router_chat,
    router_ui,
]

for router in routers:
    app.include_router(router)

# Serwowanie statycznych plików Web UI — po zarejestrowaniu wszystkich routerów API
import os
_web_dir = os.path.join(os.path.dirname(__file__), "web")
app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web")