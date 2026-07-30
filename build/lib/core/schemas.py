import json
from pydantic import BaseModel

BASE_TOOLS_SCHEMA = [
    {
        "type": "function",
        "required_tier": "butler",
        "function": {
            "name": "get_device_state",
            "description": "Zwraca dokładny obecny stan urządzenia dla podanego entity_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "entity_id": {
                        "type": ["string", "array"],
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
        "required_tier": "butler",
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
                        "type": ["string", "array"],
                        "items": {
                            "type": "string"
                        },
                        "description": "Dokładne ID encji (np. 'light.salon') lub lista ID."
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
        "required_tier": "butler",
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
        "required_tier": "butler",
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
    }
]


def get_tools_for_tier(tier: str) -> list[dict]:
    """Filtruje schematy narzędzi na podstawie poziomu uprawnień (tier).
    Zwraca kopię bez niestandardowego pola 'required_tier'."""
    tier_clearance = {"butler": 1, "regis": 2, "prime": 3}
    current_clearance = tier_clearance.get(tier, 1)
    
    filtered = []
    for tool in BASE_TOOLS_SCHEMA:
        req_tier = tool.get("required_tier", "butler")
        if tier_clearance.get(req_tier, 1) <= current_clearance:
            tool_copy = tool.copy()
            tool_copy.pop("required_tier", None)
            filtered.append(tool_copy)
    return filtered


def render_tools_for_prompt(tier: str) -> str:
    """Renderuje schematy narzędzi do formatu tekstowego kompatybilnego z Hermes/Qwen.
    
    Wymagany jest DOKŁADNY ANGIELSKI TEKST, na którym Qwen 2.5 był fine-tune'owany.
    Tłumaczenie go na polski psuje mechanizm attention dla najmniejszych modeli!
    """
    tools = get_tools_for_tier(tier)
    tools_json = json.dumps(tools, ensure_ascii=False, indent=2)
    
    return f"""# Tools
You may call one or more functions to assist with the user query. You are provided with function signatures within <tools></tools> XML tags:
<tools>
{tools_json}
</tools>
For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{{"name": <function-name>, "arguments": <args-json-object>}}
</tool_call>"""


# ─── Modele Rejestru Encji ─────────────────────────────────────────────────

class WorkerRegistrationRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy podczas rejestracji w Kontrolerze."""
    id: str
    host: str
    port: int
    model_name: str
    tier: str  # butler | regis | prime


class ToolExecutionRequest(BaseModel):
    """Payload wysyłany przez Węzeł Roboczy do proxy narzędzi w Kontrolerze."""
    tool_name: str
    arguments: dict
    tier: str = "regis"
    room: str | None = None  # kontekst pokoju Satelity — propagowany przez cały stos


class SatelliteRegistrationRequest(BaseModel):
    """Payload wysyłany przez Satelitę podczas rejestracji w Kontrolerze."""
    id: str
    room: str | None = None      # np. "salon", "sypialnia" lub None (bez filtrowania)
    type: str                     # "terminal" | "desktop" | "esp32"
    capabilities: list[str]      # np. ["text"] lub ["audio_in", "audio_out"]
    wakeword_local: bool = False
