"""Zarządzanie ścieżkami oraz trwałymi ustawieniami Aplikacji Klienckiej Regis."""

import json
import os
import uuid
from pathlib import Path
from typing import Any
from dotenv import load_dotenv

# --- 1. Inicjalizacja Środowiska i Główny Katalog Klienta ---
load_dotenv()

# Główny katalog domeny klienta (src/client)
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

    Jeśli plik nie istnieje lub nie zawiera 'node_id', generuje nowy
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

    if not merged.get("node_id"):
        merged["node_id"] = f"node-{uuid.uuid4().hex[:8]}"
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
