import asyncio
import logging
import time
import requests
from fastapi import WebSocket

from controller.integrations.base import BaseIntegration
from controller.integrations.ha_client import HomeAssistantClient
from controller.tools.tools_registry import ToolsRegistry


class ClientConnectionManager:
    """Zarządza aktywnymi połączeniami WebSocket ze Zjednoczonymi Klientami."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_command(self, client_id: str, command: str, data: dict = None) -> bool:
        from protocol.schemas import WSCommand
        if client_id in self.active_connections:
            try:
                cmd = WSCommand(command=command, data=data or {})
                await self.active_connections[client_id].send_text(cmd.model_dump_json())
                return True
            except Exception:
                self.disconnect(client_id)
        return False


# Alias dla wstecznej kompatybilności
NodeConnectionManager = ClientConnectionManager


# Globalne instancje — inicjalizowane w lifespan
ha_client: HomeAssistantClient | None = None
tools_registry: ToolsRegistry | None = None

client_manager = ClientConnectionManager()
node_manager = client_manager  # Alias dla wstecznej kompatybilności

client_registry: dict[str, dict] = {}       # Główny rejestr Zjednoczonych Klientów
node_registry = client_registry            # Alias dla wstecznej kompatybilności
worker_registry = client_registry          # Alias dla wstecznej kompatybilności
satellite_registry = client_registry       # Alias dla wstecznej kompatybilności

integration_registry: dict[str, BaseIntegration] = {}
_settings_cache: dict = {}
conversation_sessions: dict[str, list[dict]] = {}
session_last_interaction_times: dict[str, float] = {}
controller_start_time: float = time.time()

import os
from controller.config import DATA_DIR, JSONStorage

CLIENTS_CONFIG_FILE = os.path.join(DATA_DIR, "clients.json")
LEGACY_CLIENTS_CONFIG_FILE = os.path.join(DATA_DIR, "clients_config.json")
LEGACY_NODES_CONFIG_FILE = os.path.join(DATA_DIR, "nodes_config.json")

def load_persistent_clients() -> dict:
    """Ładuje trwałą konfigurację Klientów z pliku JSON (z automatyczną migracją)."""
    legacy_path = (
        LEGACY_CLIENTS_CONFIG_FILE
        if os.path.exists(LEGACY_CLIENTS_CONFIG_FILE)
        else (LEGACY_NODES_CONFIG_FILE if os.path.exists(LEGACY_NODES_CONFIG_FILE) else None)
    )
    
    if legacy_path and not os.path.exists(CLIENTS_CONFIG_FILE):
        try:
            data = JSONStorage.read_json(legacy_path, default={})
            JSONStorage.write_json(CLIENTS_CONFIG_FILE, data)
            logging.info(f"Zmigrowano profil konfiguracji z {os.path.basename(legacy_path)} do clients.json.")
            return data
        except Exception as e:
            logging.error(f"Błąd migracji konfiguracji klientów: {e}")
            
    return JSONStorage.read_json(CLIENTS_CONFIG_FILE, default={})

def save_persistent_clients(config_dict: dict) -> None:
    """Zapisuje profil konfiguracji Klientów w pliku JSON."""
    JSONStorage.write_json(CLIENTS_CONFIG_FILE, config_dict)


def get_llm_clients() -> list[dict]:
    """Zwraca listę zarejestrowanych Klientów oferujących usługę 'ollama_worker' lub 'llm'."""
    clients = []
    for client_id, client in client_registry.items():
        services = client.get("services", {})
        s_keys = services.keys() if isinstance(services, dict) else services
        if "ollama_worker" in s_keys or "llm" in s_keys or "worker" in s_keys:
            cfg = (
                services.get("ollama_worker")
                or services.get("llm")
                or services.get("worker", {})
                if isinstance(services, dict)
                else {}
            )
            port = cfg.get("port", client.get("worker_port", 8001))
            clients.append({
                "id": client.get("id", client_id),
                "host": client.get("host", "127.0.0.1"),
                "port": port,
                "base_url": f"http://{client.get('host', '127.0.0.1')}:{port}",
                "model_name": cfg.get("model_name", client.get("model_name", "qwen3.5:9b")),
                "priority": cfg.get("priority", client.get("priority", 100)),
            })
    return clients


# Aliasy dla wstecznej kompatybilności
get_llm_nodes = get_llm_clients
get_worker_nodes = get_llm_clients


def get_audio_clients() -> list[dict]:
    """Zwraca listę zarejestrowanych Klientów oferujących usługi audio (STT / TTS)."""
    clients = []
    for client_id, client in client_registry.items():
        services = client.get("services", {})
        s_keys = services.keys() if isinstance(services, dict) else services
        if "audio" in s_keys or "stt" in s_keys or "tts" in s_keys or "worker" in s_keys:
            cfg = (
                services.get("audio")
                or services.get("stt")
                or services.get("tts")
                or services.get("worker", {})
                if isinstance(services, dict)
                else {}
            )
            port = cfg.get("port", 8002)
            clients.append({
                "id": client.get("id", client_id),
                "host": client.get("host", "127.0.0.1"),
                "port": port,
                "base_url": f"http://{client.get('host', '127.0.0.1')}:{port}",
                "stt_model_size": cfg.get("stt_model_size", cfg.get("model_size", "small")),
                "tts_model_name": cfg.get("tts_model_name", cfg.get("model_name", "pl_PL-darkman-medium")),
            })
    return clients


get_audio_nodes = get_audio_clients
get_stt_nodes = get_audio_clients
get_tts_nodes = get_audio_clients


def get_satellite_clients() -> list[dict]:
    """Zwraca listę zarejestrowanych Klientów z usługą 'satellite'."""
    satellites = []
    for client_id, client in client_registry.items():
        services = client.get("services", {})
        if isinstance(services, dict) and "satellite" in services:
            s_cfg = services["satellite"]
            satellites.append({
                "id": client.get("id", client_id),
                "room": s_cfg.get("room", client.get("room")),
                "type": s_cfg.get("node_type", client.get("node_type", "desktop")),
                "capabilities": s_cfg.get("capabilities", client.get("capabilities", ["audio_input", "tts_output", "wakeword"])),
                "wakeword_local": s_cfg.get("wakeword_local", client.get("wakeword_local", True)),
                "last_seen": client.get("last_seen", time.time()),
            })
        elif isinstance(services, list) and "satellite" in services:
            satellites.append({
                "id": client.get("id", client_id),
                "room": client.get("room"),
                "type": client.get("node_type", "desktop"),
                "capabilities": client.get("capabilities", ["audio_input", "tts_output", "wakeword"]),
                "wakeword_local": client.get("wakeword_local", True),
                "last_seen": client.get("last_seen", time.time()),
            })
    return satellites


get_satellite_nodes = get_satellite_clients


def register_integration(integration: BaseIntegration) -> None:
    """Rejestruje integrację zewnętrzną w Kontrolerze."""
    global ha_client
    integration_registry[integration.id] = integration
    if integration.id == "home_assistant":
        ha_client = getattr(integration, "ha_client", None)
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


@property
def conversation_history():
    return get_session_history("default")


async def _heartbeat_loop():
    """W tle sprawdza dostępność klientów, usuwa martwych i czyści nieaktywne sesje po 60s bezczynności."""
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

        # 2. Sprawdzanie zdrowia Zjednoczonych Klientów (WebSocket timeout)
        clients = list(client_registry.values())
        for c in clients:
            cid = c.get("id")
            if not cid:
                continue
            last_seen = c.get("last_seen", now)
            if now - last_seen > 60.0:
                logging.info(f"[Heartbeat] Klient '{cid}' nie odpowiada (WebSocket timeout). Usuwam z rejestru.")
                if cid in client_registry:
                    del client_registry[cid]
                    client_manager.disconnect(cid)
                    import controller.core.event_bus as event_bus
                    await event_bus.publish({"type": "client_unregistered", "id": cid})
