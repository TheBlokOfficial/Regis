"""
Regis Controller — Serwer FastAPI i Fabryka Aplikacji ASGI.

Plik definiuje fabrykę aplikacji FastAPI (`create_app`), cykl życia usług (`lifespan`)
oraz montuje wszystkie routery API HTTP/WebSocket oraz zasoby interfejsu Web UI.
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# --- Wewnętrzne moduły Regis ---
import controller.core.app_state as app_state
import controller.core.client_store as client_store
from controller.core.heartbeat import _heartbeat_loop
from controller.config import loader as config
from controller.config.schemas import SystemSettings
from controller.integrations.loader import load_integrations
from controller.tools.tools_registry import ToolsRegistry
from protocol.discovery import get_local_ip, start_discovery_server

# --- Routery API HTTP/WS ---
from controller.api.chat import router_chat
from controller.api.clients import router_clients
from controller.api.cloud_providers import router as router_cloud_providers
from controller.api.tools import router_tools
from controller.api.ui import router_ui

# Port domyślny Kontrolera
DEFAULT_CONTROLLER_PORT = 8000


# =============================================================================
# 1. Zarządzanie Cyklem Życia Aplikacji (Lifespan Context Manager)
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Zarządza cyklem życia (start i stop) kluczowych usług Kontrolera.

    Faza 1 (Startup):
    - Wczytuje pliki konfiguracyjne.
    - Inicjalizuje i rejestruje wtyczki integracji zewnętrznych (np. Home Assistant).
    - Buduje rejestr narzędzi dla Agenta LLM (ToolsRegistry).
    - Uruchamia pętlę sprawdzania obecności połączeń (Heartbeat) oraz usługę Auto-Discovery (UDP).

    Faza 2 (Shutdown):
    - Zamyka zadania w tle i czyści zasoby przy wyłączaniu serwera.
    """
    logging.info("Rozpoczynanie inicjalizacji usług Kontrolera Regis...")

    # 1. Wczytanie głównych ustawień systemowych (silnie typowanych)
    settings = config.load(SystemSettings)

    # 2. Dynamiczne ładowanie i rejestracja integracji zewnętrznych
    for integration in load_integrations(settings):
        client_store.register_integration(integration)

    # 3. Inicjalizacja rejestru narzędzi Agenta oraz bufora ustawień
    app_state.tools_registry = ToolsRegistry()
    app_state._settings_cache.update(settings.model_dump())

    # 4. Uruchomienie zadania sprawdzania obecności połączeń w tle (Heartbeat)
    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    # 5. Uruchomienie serwera Auto-Discovery (rozgłaszanie adresu Kontrolera w sieci lokalnej UDP)
    local_ip = get_local_ip()
    discovery_url = f"http://{local_ip}:{DEFAULT_CONTROLLER_PORT}"
    start_discovery_server(discovery_url)

    logging.info(f"Usługi Kontrolera zainicjalizowane pomyślnie. Serwer Auto-Discovery nadaje na {discovery_url}.")

    yield  # Aplikacja działa i obsługuje ruch

    # --- Zatrzymywanie usług ---
    logging.info("Zamykanie usług Kontrolera Regis...")
    heartbeat_task.cancel()
    logging.info("Usługi Kontrolera zostały bezpiecznie zatrzymane.")


# =============================================================================
# 2. Fabryka Aplikacji FastAPI (Application Factory Pattern)
# =============================================================================

def create_app() -> FastAPI:
    """Tworzy i konfiguruje nową instancję aplikacji FastAPI."""
    app_instance = FastAPI(
        title="Regis Controller",
        description="Główny Serwer i Orkiestrator Agenta AI dla Inteligentnego Domu",
        version="2.0.0",
        lifespan=lifespan
    )

    # Rejestracja routerów API HTTP oraz WebSocket
    api_routers = [
        router_clients,
        router_tools,
        router_chat,
        router_cloud_providers,
        router_ui,
    ]

    for router in api_routers:
        app_instance.include_router(router)

    # Montowanie interfejsu przeglądarkowego Web UI (jeśli katalog istnieje)
    web_dir = Path(__file__).parent / "web"
    if web_dir.exists():
        app_instance.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
        logging.info(f"Zmontowano zasoby statyczne Web UI z katalogu: {web_dir}")

    return app_instance


# Główna instancja aplikacji serwerowej
app = create_app()
