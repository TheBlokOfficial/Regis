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
node_registry: dict[str, dict] = {}       # Jednolity rejestr Zjednoczonych Węzłów
worker_registry: dict[str, dict] = {}     # Kompatybilność wsteczna dla workerów
satellite_registry: dict[str, dict] = {}  # Kompatybilność wsteczna dla satelitów
integration_registry: dict[str, BaseIntegration] = {}
_settings_cache: dict = {}
conversation_sessions: dict[str, list[dict]] = {}
session_last_interaction_times: dict[str, float] = {}
controller_start_time: float = time.time()


def get_worker_nodes() -> list[dict]:
    """Zwraca listę zarejestrowanych Węzłów oferujących usługę 'worker' (LLM)."""
    workers = list(worker_registry.values())
    for node in node_registry.values():
        if "worker" in node.get("services", []):
            workers.append({
                "id": node["id"],
                "host": node["host"],
                "port": node.get("worker_port", 8001),
                "base_url": f"http://{node['host']}:{node.get('worker_port', 8001)}",
                "model_name": node.get("model_name", "qwen3.5:9b"),
                "priority": node.get("priority", 100),
            })
    return workers


def get_satellite_nodes() -> list[dict]:
    """Zwraca listę zarejestrowanych Węzłów / Satelit oferujących usługę 'satellite'."""
    satellites = list(satellite_registry.values())
    for node in node_registry.values():
        if "satellite" in node.get("services", []):
            satellites.append({
                "id": node["id"],
                "room": node.get("room"),
                "type": node.get("node_type", "desktop"),
                "capabilities": node.get("capabilities", ["audio_input", "tts_output", "wakeword"]),
                "wakeword_local": node.get("wakeword_local", True),
                "last_seen": node.get("last_seen", time.time()),
            })
    return satellites


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

        # 4. Sprawdzanie zdrowia Zjednoczonych Węzłów (port 8099)
        nodes = list(node_registry.values())
        for n in nodes:
            try:
                url = f"http://{n['host']}:{n.get('port', 8099)}/status"
                resp = await asyncio.to_thread(requests.get, url, timeout=4.0)
                resp.raise_for_status()
                node_registry[n['id']]["last_seen"] = now
            except Exception:
                # Jeśli port /status nie odpowiedział, sprawdzamy last_seen
                last_seen = n.get("last_seen", now)
                if now - last_seen > 60.0:
                    logging.info(f"[Heartbeat] Zjednoczony Węzeł '{n['id']}' nie odpowiada od 60s. Usuwam z rejestru.")
                    if n['id'] in node_registry:
                        del node_registry[n['id']]
                        import controller.event_bus as event_bus
                        await event_bus.publish({"type": "node_unregistered", "id": n['id']})



