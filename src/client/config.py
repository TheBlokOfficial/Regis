"""Zarządzanie ścieżkami oraz trwałymi ustawieniami Aplikacji Klienckiej Regis."""

import json
import os
import uuid
from pathlib import Path
from typing import Any
from dotenv import load_dotenv
from protocol.discovery import discover_controller

# --- 1. Inicjalizacja Środowiska i Główny Katalog Klienta ---
load_dotenv()
CLIENT_DIR = Path(__file__).resolve().parent

DATA_DIR = Path(os.getenv("REGIS_DATA_DIR", CLIENT_DIR / "data"))
CONFIG_DIR = Path(os.getenv("REGIS_CONFIG_DIR", CLIENT_DIR / "config"))
LOGS_DIR = Path(os.getenv("REGIS_LOGS_DIR", CLIENT_DIR / "logs"))

PROFILE = os.getenv("ACTIVE_PROFILE", "default")
SETTINGS_FILE = (
    DATA_DIR / "settings.json"
    if PROFILE == "default"
    else DATA_DIR / f"settings.{PROFILE}.json"
)

# --- 2. Wartości Domyślne ---
DEFAULT_SETTINGS: dict[str, Any] = {
    "controller_url": "auto",
}


# --- 3. Persistence API ---
def load_settings() -> dict[str, Any]:
    """Ładuje lokalną konfigurację Klienta z pliku JSON.

    Jeśli plik nie istnieje lub nie zawiera 'client_id', generuje nowy
    unikalny identyfikator i uwiecznia go na dysku.

    Returns:
        dict[str, Any]: Słownik z aktualnymi ustawieniami Klienta.
    """
    settings: dict[str, Any] = {}

    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings = json.load(f)
        except json.JSONDecodeError:
            settings = {}

    merged = {**DEFAULT_SETTINGS, **settings}

    migrated = False
    
    # Migracja ze starych kluczy z czasów węzłów
    if "node_id" in merged:
        if "client_id" not in merged:
            merged["client_id"] = merged["node_id"]
        del merged["node_id"]
        migrated = True
        
    if "instance_name" in merged:
        del merged["instance_name"] # ignorujemy starą nazwę instancji na rzecz client_id
        migrated = True

    if not merged.get("client_id"):
        merged["client_id"] = f"client-{uuid.uuid4().hex[:8]}"
        migrated = True

    if migrated:
        save_settings(merged)

    return merged


def save_settings(settings: dict[str, Any]) -> None:
    """Zapisuje podaną konfigurację do pliku settings.json.

    Args:
        settings (dict[str, Any]): Słownik konfiguracji do zapisania.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)


# --- 4. Cache i API Konfiguracyjne (Runtime) ---
_settings_cache: dict | None = None
_discovered_controller_url: str | None = None


def _get_settings() -> dict:
    """Zwraca podręczną pamięć ustawień z RAM. Wczytuje z dysku tylko za pierwszym razem."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_settings()
    return _settings_cache


def reload_settings() -> None:
    """Wymusza odświeżenie pamięci podręcznej z dysku."""
    global _settings_cache
    _settings_cache = load_settings()


def reset_discovered_controller_url() -> None:
    """Czyści zapamiętany adres Kontrolera, wymuszając ponowne Auto-Discovery przy błędzie połączenia."""
    global _discovered_controller_url
    _discovered_controller_url = None


def get_controller_url(allow_fallback: bool = False) -> str:
    """Zwraca adres URL Kontrolera z konfiguracji lub z Discovery."""
    global _discovered_controller_url
    settings = _get_settings()
    url = settings.get("controller_url", "auto")
    
    if url == "auto":
        if _discovered_controller_url:
            return _discovered_controller_url
        try:
            _discovered_controller_url = discover_controller()
            return _discovered_controller_url
        except Exception:
            if allow_fallback:
                return "http://127.0.0.1:8000"
            raise RuntimeError("Nie odnaleziono Kontrolera w sieci (Auto-Discovery).")
    return url


def _get_client_id() -> str:
    """Zwraca gwarantowane, tekstowe ID klienta."""
    return str(settings.get("client_id", "client-default"))

