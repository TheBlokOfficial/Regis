"""
Regis Controller — Serwer FastAPI i Fabryka Aplikacji ASGI.

Plik definiuje fabrykę aplikacji FastAPI (`create_app`), cykl życia usług (`lifespan`)
oraz montuje wszystkie routery API HTTP/WebSocket oraz zasoby interfejsu Web UI.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# --- Wewnętrzne moduły Regis ---
import controller.core.state as app_state
import controller.core.client_registry as client_registry
import controller.endpoints.clients as endpoints_clients
import controller.core.event_bus as event_bus
import controller.agent.session.store as session_store
from controller.config import loader as config
from controller.config.schemas import SystemSettings
from controller.integrations.loader import load_integrations
from controller.agent.tools.registry import ToolsRegistry
from protocol.discovery import get_local_ip, start_discovery_server

# --- Routery Endpoints HTTP/WS ---
from controller.endpoints.interaction import router_interaction
from controller.endpoints.clients import router_clients
from controller.endpoints.cloud import router_cloud
from controller.endpoints.tools import router_tools
from controller.endpoints.system import router_system

# Port domyślny Kontrolera
DEFAULT_CONTROLLER_PORT = 8000

# Stałe pętli Heartbeat
SESSION_IDLE_TIMEOUT = 60.0
CLIENT_TIMEOUT = 60.0
HEARTBEAT_INTERVAL = 30.0


async def _heartbeat_loop() -> None:
    """
    Główna pętla heartbeat działająca jako task asyncio w tle.

    Wykonuje dwie operacje co HEARTBEAT_INTERVAL sekund:
    1. Czyści sesje konwersacji bez aktywności przez SESSION_IDLE_TIMEOUT.
    2. Usuwa klientów którzy nie aktualizowali last_seen przez CLIENT_TIMEOUT.
    """
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        now = time.time()

        # 1. Automatyczne czyszczenie nieaktywnych sesji
        expired_sids = [
            sid for sid, t in list(session_store.session_last_interaction_times.items())
            if now - t > SESSION_IDLE_TIMEOUT
        ]
        for sid in expired_sids:
            logging.info(f"[Heartbeat] Sesja '{sid}' nieaktywna przez {SESSION_IDLE_TIMEOUT}s — czyszczę historię.")
            session_store.clear_session_history(sid)

        # 2. Sprawdzanie zdrowia klientów (WebSocket timeout)
        for c in list(client_store.client_registry.values()):
            cid = c.get("id")
            if not cid:
                continue
            last_seen = c.get("last_seen", now)
            if now - last_seen > CLIENT_TIMEOUT:
                logging.info(f"[Heartbeat] Klient '{cid}' przekroczył timeout — usuwam z rejestru.")
                client_store.client_registry.pop(cid, None)
                client_store.client_manager.disconnect(cid)
                await event_bus.publish({"type": "client_unregistered", "id": cid})


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
        app_state.register_integration(integration)

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
        router_interaction,
        router_cloud,
        router_system,
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
