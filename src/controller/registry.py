import asyncio
import logging
import time
import requests

from controller.integrations.base import BaseIntegration
from controller.integrations.ha_client import HomeAssistantClient
from controller.tools_registry import ToolsRegistry

# Globalne instancje — inicjalizowane w lifespan
ha_client: HomeAssistantClient | None = None
tools_registry: ToolsRegistry | None = None
worker_registry: dict[str, dict] = {}
satellite_registry: dict[str, dict] = {}
integration_registry: dict[str, BaseIntegration] = {}
_settings_cache: dict = {}
conversation_sessions: dict[str, list[dict]] = {}
session_last_interaction_times: dict[str, float] = {}
controller_start_time: float = time.time()


def register_integration(integration: BaseIntegration) -> None:
    """Rejestruje integrację zewnętrzną w Kontrolerze."""
    integration_registry[integration.id] = integration
    logging.info(f"Zarejestrowano integrację: {integration.name} ({integration.id})")


def get_session_history(satellite_id: str | None = None) -> list[dict]:
    """Pobiera historię konwersacji dla określonej Satelity / sesji."""
    sid = satellite_id or "default"
    return conversation_sessions.get(sid, [])


def append_to_session(satellite_id: str | None, turn: dict) -> None:
    """Dodaje turę konwersacji do sesji i uaktualnia czas interakcji."""
    sid = satellite_id or "default"
    if sid not in conversation_sessions:
        conversation_sessions[sid] = []
    conversation_sessions[sid].append(turn)
    session_last_interaction_times[sid] = time.time()


def clear_session_history(satellite_id: str | None = None) -> None:
    """Czyszczenie pamięci konkretnej sesji lub wszystkich sesji."""
    if satellite_id:
        conversation_sessions.pop(satellite_id, None)
        session_last_interaction_times.pop(satellite_id, None)
    else:
        conversation_sessions.clear()
        session_last_interaction_times.clear()


# Kompatybilność wsteczna dla właściwości globalnej
@property
def conversation_history():
    return get_session_history("default")


async def _heartbeat_loop():
    """W tle sprawdza dostępność węzłów, usuwa martwe i czyści nieaktywne sesje po 60s bezczynności."""
    while True:
        await asyncio.sleep(30)
        
        # 1. Automatyczne czyszczenie nieaktywnych sesji
        now = time.time()
        expired_sids = [
            sid for sid, t in list(session_last_interaction_times.items())
            if now - t > 60.0
        ]
        for sid in expired_sids:
            logging.info(f"Brak interakcji przez 60 sekund w sesji '{sid}'. Automatyczne czyszczenie pamięci.")
            clear_session_history(sid)
            
        # 2. Sprawdzanie zdrowia węzłów
        workers = list(worker_registry.values())
        for w in workers:
            try:
                url = f"{w['base_url']}/v1/health"
                resp = await asyncio.to_thread(requests.get, url, timeout=5.0)
                resp.raise_for_status()
            except Exception as e:
                logging.warning(f"[Heartbeat] Węzeł {w['id']} nie odpowiada ({type(e).__name__}). Usuwam z rejestru.")
                if w['id'] in worker_registry:
                    del worker_registry[w['id']]
                    import controller.event_bus as event_bus
                    await event_bus.publish({"type": "worker_unregistered", "id": w['id']})



