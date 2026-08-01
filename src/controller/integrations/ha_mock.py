import json
import os
import logging
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(BASE_DIR, "data", "ha_state.json")

DEFAULT_STATE = {
    "light.salon": "off",
    "light.kuchnia": "off",
    "sensor.temperatura_salon": 21.5,
    "climate.ogrzewanie": "off"
}

class HomeAssistantMock:
    """Mock klienta Home Assistanta na potrzeby testów bez dostępu do prawdziwego serwera."""

    def __init__(self):
        logging.info("Zainicjalizowano HomeAssistantMock (Środowisko Testowe)")

    def _load_state(self) -> dict[str, Any]:
        """Pobiera lokalny stan mocka z pliku ha_state.json."""
        if not os.path.exists(STATE_FILE):
            self._save_state(DEFAULT_STATE)
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_state(self, state: dict[str, Any]) -> None:
        """Zapisuje aktualny stan mocka do pliku."""
        data_dir = os.path.dirname(STATE_FILE)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4)

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Mock pobierania stanów z lokalnego pliku JSON."""
        state = self._load_state()
        return {k: {"state": v, "friendly_name": k} for k, v in state.items()}

    def execute_action(self, action: str, entity_id: str | list[str], parameters: dict[str, Any] | None = None) -> bool:
        """Mock wykonywania akcji na encjach w lokalnym stanie."""
        if isinstance(entity_id, list):
            all_success = True
            for single_id in entity_id:
                if not self.execute_action(action, single_id, parameters):
                    all_success = False
            return all_success

        state = self._load_state()
        
        if action == "turn_on" and entity_id in state:
            state[entity_id] = "on"
            logging.info(f"[HA-MOCK] Wykonano sprzętowo: Włączono {entity_id}")
        elif action == "turn_off" and entity_id in state:
            state[entity_id] = "off"
            logging.info(f"[HA-MOCK] Wykonano sprzętowo: Wyłączono {entity_id}")
        elif action == "set_temperature":
            logging.info(f"[HA-MOCK] Wykonano sprzętowo: Zmiana temperatury dla {entity_id}")
        else:
            logging.error(f"[HA-MOCK] Błąd: Nieznana akcja {action} dla encji {entity_id}")
            return False
            
        self._save_state(state)
        return True
