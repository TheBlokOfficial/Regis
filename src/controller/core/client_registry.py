"""
Rejestr podłączonych klientów w pamięci oraz kwerendy po typie usługi.
"""
import time

# Główny rejestr aktywnych klientów: {client_id: {id, host, services, last_seen}}
# Uzupełniany przy rejestracji WebSocket, czyszczony przez heartbeat.
client_registry: dict[str, dict] = {}


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
