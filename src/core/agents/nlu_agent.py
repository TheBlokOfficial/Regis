import json
import logging
import requests
from requests.exceptions import RequestException
from typing import Any

from core import config

logger = logging.getLogger(__name__)

class NLUAgent:
    """Agent NLU działający w oparciu o strukturalne wyjście z góry narzuconego schematu (JSON Schema)."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def generate_response(self, messages: list[dict], tools_registry, on_tool_call: Any, on_thought_token: Any, on_content_token: Any, on_raw_tool_call: Any = None) -> str:
        """Szybka ścieżka generacji. Używa Structured Outputs do wydobycia intencji."""
        settings = config.load_settings()
        chat_url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/chat"

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": True,
            "keep_alive": -1,
            "format": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["turn_on", "turn_off", "toggle", "set_value", "unknown"]},
                    "entity_id": {"type": "string"},
                    "parameter_value": {"type": "integer"}
                },
                "required": ["action", "entity_id"]
            },
            "options": {
                "temperature": 0.0,
                "num_predict": 512,
                "think": False
            }
        }
        
        try:
            response = requests.post(chat_url, json=payload, stream=True, timeout=30)
            response.raise_for_status()
            
            content = ""
            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        content += chunk
                        if on_thought_token:
                            on_thought_token(chunk)
                except json.JSONDecodeError:
                    pass
            
            logger.debug(f"NLU surowa odpowiedź modelu: {content!r}")
            try:
                intent = json.loads(content)
            except json.JSONDecodeError as e:
                logger.warning(
                    f"NLU JSONDecodeError: nie można sparsować odpowiedzi modelu. "
                    f"Wyjątek: {e} | treść: {content!r}"
                )
                intent = {"action": "unknown"}
                
            action = intent.get("action", "unknown")
            target_entity = intent.get("entity_id", "")
            
            if action == "unknown" or not target_entity:
                return ""
                
            tool_args = {"action": action, "entity_id": target_entity, "parameters": {}}
            args_str = f"action='{action}', entity_id='{target_entity}'"
            
            if action == "set_value" and intent.get("parameter_value") is not None:
                val = intent["parameter_value"]
                domain = target_entity.split(".")[0] if "." in target_entity else "light"
                
                # Tablica routingowa w celu uniknięcia drabinek IF-ELSE
                domain_map = {
                    "light": {"action": "turn_on", "param_key": "brightness_pct", "val_modifier": lambda x: x},
                    "media_player": {"action": action, "param_key": "volume_level", "val_modifier": lambda x: x / 100.0},
                    "climate": {"action": action, "param_key": "temperature", "val_modifier": lambda x: x}
                }
                
                if domain in domain_map:
                    cfg = domain_map[domain]
                    tool_args["action"] = cfg["action"]
                    mapped_val = cfg["val_modifier"](val)
                    tool_args["parameters"][cfg["param_key"]] = mapped_val
                    args_str = f"action='{tool_args['action']}', entity_id='{target_entity}', {cfg['param_key']}={mapped_val}"
                    
            log_text = f"> Lokaj (NLU) wywołuje: execute_action({args_str})"
            if on_tool_call:
                on_tool_call(log_text)
                    
                tool_result = tools_registry.execute_tool("execute_action", tool_args)
                
                if on_tool_call:
                    on_tool_call(f"< Kontroler zwrócił: {tool_result}")
                
                if on_raw_tool_call:
                    on_raw_tool_call({
                        "name": "execute_action",
                        "arguments": tool_args,
                        "result": tool_result
                    })
                
            return ""
            
        except RequestException as e:
            logging.error(f"Błąd NLU: {e}")
            return "Błąd komunikacji z modułem NLU."
