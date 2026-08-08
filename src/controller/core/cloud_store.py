"""
Magazyn konfiguracji dostawców chmurowych (cloud_providers.json).

Odpowiada za trwały zapis i odczyt ustawień dostawców zewnętrznych (np. OpenRouter API Key).
"""
import logging
import os
from pathlib import Path

from controller.config import loader as config
from controller.config.loader import JSONStorage

logger = logging.getLogger(__name__)

PROVIDERS_FILE = Path(config.DATA_DIR) / "cloud_providers.json"

_cloud_providers_cache: list[dict] = []
_providers_loaded = False


def get_cloud_providers() -> list[dict]:
    """Zwraca listę dostawców chmurowych z pamięci podręcznej (ładuje ją przy pierwszym wywołaniu)."""
    global _providers_loaded
    if not _providers_loaded:
        reload_cloud_providers()
    return _cloud_providers_cache


def reload_cloud_providers() -> None:
    """Odświeża pamięć podręczną z pliku cloud_providers.json (oraz migruje .env jeśli to pierwsze uruchomienie)."""
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
                "priority": 50
            })
            JSONStorage.write_json(PROVIDERS_FILE, migrated)
            logger.info("Zmigrowano klucz OpenRouter z .env do cloud_providers.json.")

    data = JSONStorage.read_json(PROVIDERS_FILE, default=[])
    _cloud_providers_cache = data if isinstance(data, list) else []
    _providers_loaded = True


def save_cloud_providers(data: list[dict]) -> bool:
    """Zapisuje listę dostawców chmurowych do pliku i odświeża pamięć podręczną."""
    try:
        JSONStorage.write_json(PROVIDERS_FILE, data)
        reload_cloud_providers()
        return True
    except Exception as e:
        logger.error(f"Błąd zapisu cloud_providers.json: {e}")
        return False
