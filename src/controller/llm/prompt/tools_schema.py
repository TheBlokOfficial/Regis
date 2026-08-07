import json

BASE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_device_state",
            "description": "Zwraca dokładny obecny stan urządzenia dla podanego entity_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Dokładne ID encji (np. 'light.salon') lub lista ID (np. ['light.1', 'light.2'])."
                    }
                },
                "required": ["entity_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_action",
            "description": "Wykonuje akcję na urządzeniu. Bierz entity_id wyłącznie ze swojego Globalnego Menu. Jeśli ustawiasz parametry (np. jasność), akcja musi być 'turn_on'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["turn_on", "turn_off", "toggle"],
                        "description": "Typ akcji: 'turn_on', 'turn_off' lub 'toggle'."
                    },
                    "entity_id": {
                        "type": "array",
                        "items": {
                            "type": "string"
                        },
                        "description": "Dokładne ID encji (np. 'light.salon') lub lista. Architektura systemu: Sterowanie nadrzędną Grupą automatycznie kaskaduje akcję do wszystkich urządzeń podrzędnych. Podawanie w liście urządzeń podrzędnych obok ich Grupy jest powielaniem polecenia - podawaj tylko Grupę."
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Opcjonalne parametry natywne Home Assistant (np. 'brightness' w skali 0-255, 'brightness_pct' w skali 0-100)."
                    }
                },
                "required": ["action", "entity_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Zwraca bieżącą datę i czas systemowy (razem z dniem tygodnia).",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Zwraca aktualne informacje o pogodzie w podanym mieście.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "Nazwa miasta, np. 'Warszawa'."
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_phone_battery",
            "description": "Zwraca aktualny poziom baterii w telefonie użytkownika (Pixel 9a). Zwraca wartość w procentach oraz informację, czy się ładuje.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]


def get_tools_schema(names: list[str] | None = None) -> list[dict]:
    """Zwraca kopię schematów dostępnych narzędzi w systemie.
    Jeśli podano listę 'names', zwraca tylko narzędzia o podanych nazwach.
    """
    if names is None:
        return [tool.copy() for tool in BASE_TOOLS_SCHEMA]
    return [tool.copy() for tool in BASE_TOOLS_SCHEMA if tool["function"]["name"] in names]
