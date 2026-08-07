import logging
import os
from pathlib import Path

from controller.llm.backends.base import LLMBackend
from controller.llm.backends.openrouter import OpenRouterBackend
from controller.llm.backends.ollama import OllamaBackend

import controller.core.client_registry as registry
from controller.config import loader as config, JSONStorage

PROVIDERS_FILE = Path(config.DATA_DIR) / "cloud_providers.json"

_cloud_providers_cache: list[dict] = []
_providers_loaded = False

def get_cloud_providers() -> list[dict]:
    """Zwraca listę dostawców chmurowych z pamięci podręcznej (ładuje ją przy pierwszym wywołaniu)."""
    global _providers_loaded
    if not _providers_loaded:
        reload_cloud_providers()
    return _cloud_providers_cache

def reload_cloud_providers():
    global _cloud_providers_cache, _providers_loaded
    
    # Auto-migracja z .env przy pierwszym uruchomieniu
    if not PROVIDERS_FILE.exists():
        migrated = []
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        model = os.environ.get("OPENROUTER_MODEL", "qwen/qwen-2.5-72b-instruct")
        if api_key:
            migrated.append({
                "id": "auto_openrouter",
                "type": "openrouter",
                "api_key": api_key,
                "model": model,
                "mode": "extended",
                "priority": 50
            })
            JSONStorage.write_json(PROVIDERS_FILE, migrated)
            logging.info("Zmigrowano klucz OpenRouter z .env do cloud_providers.json.")
        
    data = JSONStorage.read_json(PROVIDERS_FILE, default=[])
    _cloud_providers_cache = data if isinstance(data, list) else []
    _providers_loaded = True

def save_cloud_providers(data: list[dict]) -> bool:
    """Zapisuje listę dostawców chmurowych do pliku i odświeża pamięć podręczną."""
    success = JSONStorage.write_json(PROVIDERS_FILE, data)
    if success:
        reload_cloud_providers()
    return success

def get_llm_backend() -> LLMBackend | None:
    """Zwraca najlepszy dostępny backend LLM według priorytetu."""
    if not _providers_loaded:
        reload_cloud_providers()

    candidates: list[tuple[int, LLMBackend, dict]] = []

    # 1. Zarejestrowane Węzły Robocze (Workery)
    for worker in registry.worker_registry.values():
        prio = worker.get("priority", 10)
        mode = worker.get("mode", "extended")
        candidates.append((prio, OllamaBackend(model_name="worker", mode=mode), worker))

    # 2. Providery chmurowe z rejestru
    for cp in _cloud_providers_cache:
        if cp.get("type") == "openrouter" and cp.get("api_key") and cp.get("model"):
            try:
                backend = OpenRouterBackend(
                    api_key=cp["api_key"], 
                    model_name=cp["model"],
                    mode=cp.get("mode", "extended")
                )
                if backend.is_available():
                    candidates.append((cp.get("priority", 50), backend, cp))
            except Exception as e:
                logging.warning(f"Błąd ładowania chmury {cp.get('id')}: {e}")

    if not candidates:
        return None

    # Sortowanie malejąco według priority
    candidates.sort(key=lambda item: item[0], reverse=True)
    selected_prio, selected_backend, meta = candidates[0]
    
    logging.debug(f"Wybrano LLM Backend: {selected_backend.get_provider_name()} z priorytetem {selected_prio}")
    return selected_backend

def has_llm_provider() -> bool:
    return get_llm_backend() is not None
