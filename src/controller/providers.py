import logging
import os
import json
from pathlib import Path

from controller.llm_backends.base import LLMBackend
from controller.openrouter_backend import OpenRouterBackend
from controller.llm_backends.ollama import OllamaBackend
import controller.registry as registry
from core import config

_cloud_providers_cache: list[dict] = []
_providers_loaded = False

def reload_cloud_providers():
    global _cloud_providers_cache, _providers_loaded
    providers_file = Path(config.DATA_DIR) / "cloud_providers.json"
    
    # Auto-migracja z .env przy pierwszym uruchomieniu
    if not providers_file.exists():
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
            try:
                providers_file.parent.mkdir(parents=True, exist_ok=True)
                providers_file.write_text(json.dumps(migrated, indent=2, ensure_ascii=False), encoding="utf-8")
                logging.info("Zmigrowano klucz OpenRouter z .env do cloud_providers.json.")
            except Exception as e:
                logging.error(f"Błąd zapisu migracji: {e}")
        
    if providers_file.exists():
        try:
            data = json.loads(providers_file.read_text(encoding="utf-8"))
            _cloud_providers_cache = data if isinstance(data, list) else []
        except Exception as e:
            logging.error(f"Błąd odczytu cloud_providers.json: {e}")
            _cloud_providers_cache = []
    else:
        _cloud_providers_cache = []
        
    _providers_loaded = True

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
    
    # Tymczasowo zapisujemy mode w wybranym backendzie, żeby router wiedział jak się zachować, jeśli by potrzebował.
    # Właściwie backendy same to będą już mieć w swojej hermetycznej konfiguracji.
    logging.debug(f"Wybrano LLM Backend: {selected_backend.get_provider_name()} z priorytetem {selected_prio}")
    return selected_backend

def has_llm_provider() -> bool:
    return get_llm_backend() is not None
