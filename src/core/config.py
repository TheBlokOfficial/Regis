import os
import sys
import json
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
ALIASES_FILE = os.path.join(CONFIG_DIR, "aliases.json")
def load_settings() -> dict[str, Any]:
    """Ładuje główne ustawienia programu z fallbackiem na wartości domyślne.
    
    Returns:
        dict[str, Any]: Słownik z konfiguracją systemu.
    """
    default_settings = {
        "openrouter_priority": 50,
        "worker_priority": 100,
        "history_limit": 10,
        "ha_url": "http://192.168.0.50:8123",
        "ha_token": "TWÓJ_TOKEN_TUTAJ",
        "server_url": "auto",
        "controller_url": "auto",
        "ollama_url": "http://127.0.0.1:11434"
    }
    if not os.path.exists(SETTINGS_FILE):
        return default_settings
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        try:
            settings = json.load(f)
            return {**default_settings, **settings}
        except json.JSONDecodeError:
            return default_settings

def save_settings(settings: dict[str, Any]) -> None:
    """Zapisuje ustawienia do pliku konfiguracyjnego.
    
    Args:
        settings (dict[str, Any]): Aktualny stan konfiguracji do zapisu.
    """
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)

def load_aliases() -> dict[str, str]:
    """Ładuje zdefiniowane w pliku aliasy nazw urządzeń HA.
    
    Returns:
        dict[str, str]: Słownik mapujący np. "light.xyz" -> "Lampa".
    """
    if not os.path.exists(ALIASES_FILE):
        return {}
    with open(ALIASES_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def load_virtual_groups() -> dict[str, list[str]]:
    """Ładuje wirtualne grupy urządzeń z pliku konfiguracyjnego.
    
    Returns:
        dict[str, list[str]]: Słownik grup, np. {"light.moj_pokoj": ["light.id1", "light.id2"]}
    """
    groups_file = os.path.join(CONFIG_DIR, "virtual_groups.json")
    if not os.path.exists(groups_file):
        return {}
    with open(groups_file, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def load_rooms() -> dict[str, list[str]]:
    """Ładuje mapowanie pokojów na listy entity_id z data/rooms.json.

    Plik rooms.json jest wewnętrzną konfiguracją Regis — niezależną od HA
    i od konkretnej integracji (MANIFEST.md §3.5).

    Returns:
        dict[str, list[str]]: Słownik mapujący nazwę pokoju na listę entity_id,
        np. {"salon": ["light.salon_lampa", "switch.salon_tv"]}
    """
    rooms_file = os.path.join(CONFIG_DIR, "rooms.json")
    if not os.path.exists(rooms_file):
        return {}
    with open(rooms_file, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

