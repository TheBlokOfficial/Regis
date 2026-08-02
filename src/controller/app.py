"""
Regis Controller — Serce i punkt wejścia serwera FastAPI na Raspberry Pi 5.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core import config
from core.discovery import get_local_ip, start_discovery_server
from core.logger import setup_logging
from controller import registry
from controller.integrations.loader import load_integrations
from controller.tools_registry import ToolsRegistry
from controller.routers.chat import router_chat
from controller.routers.nodes import router_nodes
from controller.routers.satellites import router_satellites
from controller.routers.tools import router_tools
from controller.routers.ui import router_ui
from controller.routers.workers import router_workers
from controller.routers.cloud_providers import router as router_cloud_providers

# ─── 1. Inicjalizacja Logowania i Stałych ──────────────────────────────────
setup_logging("controller")

DEFAULT_CONTROLLER_PORT = 8000


# ─── 2. Cykl Życia Aplikacji (Lifespan) ────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uruchamia i zatrzymuje kluczowe usługi Kontrolera."""
    # Ładowanie konfiguracji systemowej
    settings = config.load_settings()
    aliases = config.load_aliases()
    virtual_groups = config.load_virtual_groups()
    rooms = config.load_rooms()

    # Dynamiczna inicjalizacja i rejestracja integracji zewnętrznych
    for integration in load_integrations(settings, aliases, virtual_groups):
        registry.register_integration(integration)

    # Inicjalizacja rejestru narzędzi AI i bufora ustawień
    registry.tools_registry = ToolsRegistry(rooms=rooms)
    registry._settings_cache.update(settings)

    # Uruchomienie pętli w tle (Heartbeat + Auto-Discovery)
    heartbeat_task = asyncio.create_task(registry._heartbeat_loop())

    local_ip = get_local_ip()
    discovery_url = f"http://{local_ip}:{DEFAULT_CONTROLLER_PORT}"
    start_discovery_server(discovery_url)

    logging.info("Regis Controller uruchomiony.")

    yield  # Serwer aktywny i gotowy na zapytania

    # Zamknięcie usług przy zatrzymywaniu serwera
    heartbeat_task.cancel()
    logging.info("Regis Controller zatrzymany.")


# ─── 3. Tworzenie Aplikacji FastAPI i Montowanie Routerów ─────────────────
app = FastAPI(title="Regis Controller", lifespan=lifespan)

# Rejestracja routerów API
routers = [
    router_nodes,
    router_workers,
    router_satellites,
    router_tools,
    router_chat,
    router_cloud_providers,
    router_ui,  # router_ui musi być zarejestrowany przed app.mount StaticFiles
]

for router in routers:
    app.include_router(router)

# ─── 4. Serwowanie Zasobów Statycznych Web UI ─────────────────────────────
_web_dir = Path(__file__).parent / "web"
app.mount("/", StaticFiles(directory=_web_dir, html=True), name="web")