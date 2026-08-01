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
conversation_history: list[dict] = []
last_interaction_time: float = 0.0
controller_start_time: float = time.time()


def register_integration(integration: BaseIntegration) -> None:
    """Rejestruje integrację zewnętrzną w Kontrolerze."""
    integration_registry[integration.id] = integration
    logging.info(f"Zarejestrowano integrację: {integration.name} ({integration.id})")

# Priorytety tierów usunięto zgodnie z Phase 1

async def _heartbeat_loop():
    """W tle sprawdza dostępność węzłów, usuwa martwe i czyści historię po 60s bezczynności."""
    import time
    global last_interaction_time
    
    while True:
        await asyncio.sleep(30)
        
        # 1. Automatyczne czyszczenie pamięci
        if conversation_history and (time.time() - last_interaction_time > 60.0):
            logging.info("Brak interakcji przez 60 sekund. Automatyczne czyszczenie pamięci (historii).")
            conversation_history.clear()
            
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



