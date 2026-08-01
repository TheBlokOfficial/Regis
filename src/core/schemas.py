import json
from pydantic import BaseModel

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


def get_tools_schema() -> list[dict]:
    """Zwraca kopię schematów dostępnych narzędzi w systemie."""
    return [tool.copy() for tool in BASE_TOOLS_SCHEMA]


def render_tools_for_prompt() -> str:
    """Renderuje schematy narzędzi do formatu tekstowego kompatybilnego z Hermes/Qwen.
    
    Wymagany jest DOKŁADNY ANGIELSKI TEKST, na którym Qwen 2.5 był fine-tune'owany.
    Tłumaczenie go na polski psuje mechanizm attention dla najmniejszych modeli!
    """
    tools = get_tools_schema()
    tools_json = json.dumps(tools, ensure_ascii=False, indent=2)
    
    return f"""# Tools
You may call one or more functions to assist with the user query. You are provided with function signatures within <tools></tools> XML tags:
<tools>
{tools_json}
</tools>
For each function call, return a json object with function name and arguments within <action></action> XML tags:
<action>
{{"name": <function-name>, "arguments": <args-json-object>}}
</action>
The result of the tool execution will be provided to you within <tool_response></tool_response> tags."""


# ─── Modele Rejestru Encji ─────────────────────────────────────────────────

class WorkerRegistrationRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy podczas rejestracji w Kontrolerze."""
    id: str
    host: str
    port: int
    model_name: str
    priority: int = 100  # Wyższa wartość = wyższa ważność (100 = GPU PC, 50 = OpenRouter cloud, 10 = RPi fallback)


class ToolExecutionRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy do proxy narzędzi w Kontrolerze."""
    tool_name: str
    arguments: dict
    room: str | None = None  # kontekst pokoju Satelity — propagowany przez cały stos


class SatelliteRegistrationRequest(BaseModel):
    """Payload wysyłany przez Satelitę podczas rejestracji w Kontrolerze."""
    id: str
    room: str | None = None      # np. "salon", "sypialnia" lub None (bez filtrowania)
    type: str                     # "terminal" | "desktop" | "esp32"
    capabilities: list[str]      # np. ["text"] lub ["audio_in", "audio_out"]
    wakeword_local: bool = False


class NodeRegistrationRequest(BaseModel):
    """Payload wysyłany przez Węzeł podczas zbiorczej rejestracji w Kontrolerze."""
    id: str
    name: str | None = None
    host: str
    port: int = 8099
    services: list[str] = ["worker", "satellite"]  # oferowane usługi: "worker", "satellite"
    
    # Metadane usługi Workera (LLM)
    model_name: str | None = None
    priority: int = 100

    # Metadane usługi Satelity (Audio/VAD)
    room: str | None = None
    node_type: str = "desktop"
    capabilities: list[str] = ["audio_input", "tts_output", "wakeword"]
    wakeword_local: bool = True
