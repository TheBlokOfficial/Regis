import os
import pytest
from controller import config

def test_load_settings_defaults():
    # Zmieniamy ścieżkę pliku na nieistniejącą, aby wymusić domyślne ustawienia
    original_file = config.SETTINGS_FILE
    config.SETTINGS_FILE = "non_existent_settings.json"
    
    try:
        settings = config.load_settings()
        assert settings["openrouter_priority"] == 50
        assert settings["worker_priority"] == 100
        assert settings["ha_url"] == "http://192.168.0.50:8123"
    finally:
        config.SETTINGS_FILE = original_file

def test_load_aliases_defaults():
    original_file = config.ALIASES_FILE
    config.ALIASES_FILE = "non_existent_aliases.json"
    
    try:
        aliases = config.load_aliases()
        assert aliases == {}
    finally:
        config.ALIASES_FILE = original_file
