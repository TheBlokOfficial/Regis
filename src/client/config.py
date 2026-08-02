import os
import json
import uuid
from typing import Any
from dotenv import load_dotenv

load_dotenv()

WORK_DIR = os.getcwd()

DATA_DIR = os.getenv("REGIS_DATA_DIR", os.path.join(WORK_DIR, "data"))
CONFIG_DIR = os.getenv("REGIS_CONFIG_DIR", os.path.join(WORK_DIR, "config"))
PROFILE = os.getenv("ACTIVE_PROFILE", "default")

if PROFILE == "default":
    SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
else:
    SETTINGS_FILE = os.path.join(DATA_DIR, f"settings.{PROFILE}.json")


def load_settings() -> dict[str, Any]:
    """Ładuje lokalne ustawienia Węzła z fallbackiem na wartości domyślne.
    Jeśli node_id nie istnieje, generuje stały unikalny identyfikator i uwiecznia w konfiguracji.
    
    Returns:
        dict[str, Any]: Słownik z lokalną konfiguracją Węzła.
    """
    default_settings = {
        "controller_url": "auto",
        "ollama_url": "http://127.0.0.1:11434",
        "worker_port": 8001
    }
    settings = {}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            try:
                settings = json.load(f)
            except json.JSONDecodeError:
                settings = {}

    merged = {**default_settings, **settings}
    if "node_id" not in merged or not merged["node_id"]:
        merged["node_id"] = f"node-{uuid.uuid4().hex[:8]}"
        save_settings(merged)

    return merged


def save_settings(settings: dict[str, Any]) -> None:
    """Zapisuje lokalne ustawienia Węzła do pliku konfiguracyjnego.
    
    Args:
        settings (dict[str, Any]): Aktualny stan konfiguracji do zapisu.
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
