"""
Rejestr podłączonych klientów, persystencja ich konfiguracji oraz kwerendy po typie usługi.

Przechowuje runtime-owy rejestr aktywnych klientów (uzupełniany przy rejestracji przez WebSocket)
oraz persystentną konfigurację klientów zapisywaną na dysk (clients.json).
"""
import logging
import os
import time

from controller.config.loader import DATA_DIR, JSONStorage

CLIENTS_CONFIG_FILE = os.path.join(DATA_DIR, "clients.json")
LEGACY_CLIENTS_CONFIG_FILE = os.path.join(DATA_DIR, "clients_config.json")
LEGACY_NODES_CONFIG_FILE = os.path.join(DATA_DIR, "nodes_config.json")

# Główny rejestr aktywnych klientów: {client_id: {id, host, services, last_seen}}
# Uzupełniany przy rejestracji WebSocket, czyszczony przez heartbeat.
client_registry: dict[str, dict] = {}


# ─── Persystencja ─────────────────────────────────────────────────────────────

def load_persistent_clients() -> dict:
    """Ładuje trwałą konfigurację Klientów z pliku JSON (z automatyczną migracją starych formatów)."""
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


# ─── Rejestracja integracji ───────────────────────────────────────────────────

def register_integration(integration) -> None:
    """Rejestruje integrację zewnętrzną w Kontrolerze."""
    import controller.core.app_state as app_state
    app_state.integration_registry[integration.id] = integration
    if integration.id == "home_assistant":
        app_state.ha_client = getattr(integration, "ha_client", None)
    logging.info(f"Zarejestrowano integrację: {integration.name} ({integration.id})")


# ─── Kwerendy po typie usługi ─────────────────────────────────────────────────

def get_llm_clients() -> list[dict]:
    """Zwraca listę zarejestrowanych Klientów oferujących usługę LLM (ollama_worker / llm / worker)."""
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
