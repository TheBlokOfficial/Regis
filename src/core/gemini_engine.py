import json
import logging
import requests
from requests.exceptions import RequestException
from typing import Any
import datetime
import os

from core.exceptions import LLMConnectionError

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

class GeminiEngine:
    """Silnik odpowiadający za komunikację z chmurowym API Gemini (kompatybilność OpenAI)."""

    def __init__(self, model_name: str, tier: str, temperature: float = 0.5, tool_temperature: float = 0.1, history_limit: int = 10):
        self.model_name = model_name
        self.tier = tier
        self.temperature = temperature
        self.tool_temperature = tool_temperature
        self.history_limit = history_limit
        self.history = []
        logging.info(f"Zainicjalizowano GeminiEngine: Model={model_name}, Tier={self.tier}, Temp={temperature}")

    @staticmethod
    def get_available_models() -> list[str]:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return ["gemini-1.5-pro-latest", "gemini-1.5-flash-latest"]
            
        try:
            # Używamy standardowego endpointu Gemini (nie-OpenAI) żeby wylistować modele
            url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                models = response.json().get("models", [])
                valid_models = []
                for m in models:
                    if "generateContent" in m.get("supportedGenerationMethods", []):
                        name = m.get("name", "")
                        if name.startswith("models/"):
                            name = name.replace("models/", "")
                        valid_models.append(name)
                # Sortujemy zeby pokazac Pro na poczatku
                return sorted(valid_models, reverse=True)
        except Exception as e:
            logging.error(f"Błąd pobierania modeli Gemini: {e}")
            
        return ["gemini-1.5-pro-latest", "gemini-1.5-flash-latest"]

    def _build_system_prompt(self) -> str:
        """Dynamicznie wczytuje prompt bazowy i warstwy z plików."""
        from core import config
        base_path = os.path.join(config.CONFIG_DIR, "prompts", "base_system.md")
        tier_path = os.path.join(config.CONFIG_DIR, "prompts", f"tier_{self.tier}.md")
        
        base_prompt = "Jesteś asystentem domowym."
        tier_prompt = "Wykonujesz polecenia."
        
        try:
            with open(base_path, "r", encoding="utf-8") as f:
                base_prompt = f.read().strip()
        except Exception as e:
            logging.warning(f"Błąd ładowania {base_path}: {e}")
            
        try:
            with open(tier_path, "r", encoding="utf-8") as f:
                tier_prompt = f.read().strip()
        except Exception as e:
            logging.warning(f"Błąd ładowania {tier_path}: {e}")
            
        return f"{base_prompt}\n{tier_prompt}"

    def clear_history(self) -> None:
        self.history = []
        logging.info("Wyczyszczono historię konwersacji Gemini.")

    def generate_response(self, prompt: str, tools_registry, status_callback: Any = None, stream_callback: Any = None, final_response_callback: Any = None) -> str:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMConnectionError("Brak klucza GEMINI_API_KEY w środowisku. Przejdź do '/provider' i wpisz klucz API.")

        prompt_to_use = self._build_system_prompt()
        messages = [{"role": "system", "content": prompt_to_use}]
        
        for m in self.history:
            if m["role"] not in ["tool_log"]:
                msg_dict = {"role": m["role"], "content": m.get("content", "")}
                if "tool_calls" in m:
                    msg_dict["tool_calls"] = m["tool_calls"]
                if "tool_call_id" in m:
                    msg_dict["tool_call_id"] = m["tool_call_id"]
                if "name" in m:
                    msg_dict["name"] = m["name"]
                
                if m["role"] == "user" and "timestamp" in m:
                    msg_dict["content"] = f"[{m['timestamp']}] {msg_dict['content']}"
                
                messages.append(msg_dict)

        now = datetime.datetime.now().strftime("%H:%M:%S")
        messages.append({"role": "user", "content": f"[{now}] {prompt}"})
        self.history.append({"role": "user", "content": prompt, "timestamp": now})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        while True:
            payload = {
                "model": self.model_name,
                "messages": messages,
                "stream": True,
                "temperature": self.temperature
            }
            
            if tools_registry.tools_schema:
                payload["tools"] = tools_registry.tools_schema

            try:
                response = requests.post(GEMINI_API_URL, headers=headers, json=payload, timeout=120, stream=True)
                if response.status_code != 200:
                    raise LLMConnectionError(f"HTTP {response.status_code}: {response.text}")

                full_content = ""
                tool_calls_accumulator = {} 

                for line in response.iter_lines():
                    if not line:
                        continue
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith("data: "):
                        data_str = decoded_line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                            
                        try:
                            chunk = json.loads(data_str)
                            if not chunk.get("choices"):
                                continue
                            delta = chunk["choices"][0].get("delta", {})
                            
                            if "content" in delta and delta["content"]:
                                piece = delta["content"]
                                full_content += piece
                                if stream_callback:
                                    stream_callback(piece, False)
                                    
                            if "tool_calls" in delta:
                                for tc_pos, tc in enumerate(delta["tool_calls"]):
                                    idx = tc.get("index", tc_pos)
                                    if idx not in tool_calls_accumulator:
                                        # Kopiujemy wszystkie oryginalne pola z pierwszej paczki (np. thought_signature)
                                        tool_calls_accumulator[idx] = tc.copy()
                                        if "id" not in tool_calls_accumulator[idx]:
                                            tool_calls_accumulator[idx]["id"] = f"call_{idx}"
                                        if "type" not in tool_calls_accumulator[idx]:
                                            tool_calls_accumulator[idx]["type"] = "function"
                                        if "function" not in tool_calls_accumulator[idx]:
                                            tool_calls_accumulator[idx]["function"] = {"name": "", "arguments": ""}
                                        else:
                                            # Kopiujemy function zeby nie zepsuc oryginalnej referencji
                                            tool_calls_accumulator[idx]["function"] = tc["function"].copy()
                                            if "name" not in tool_calls_accumulator[idx]["function"]:
                                                tool_calls_accumulator[idx]["function"]["name"] = ""
                                            if "arguments" not in tool_calls_accumulator[idx]["function"]:
                                                tool_calls_accumulator[idx]["function"]["arguments"] = ""
                                    else:
                                        # Paczka kolejna - doklejamy tylko argumenty
                                        if "function" in tc:
                                            if "name" in tc["function"] and tc["function"]["name"]:
                                                tool_calls_accumulator[idx]["function"]["name"] += tc["function"]["name"]
                                            if "arguments" in tc["function"] and tc["function"]["arguments"]:
                                                tool_calls_accumulator[idx]["function"]["arguments"] += tc["function"]["arguments"]
                                        
                        except json.JSONDecodeError:
                            continue

                response_text = full_content
                
                final_tool_calls = []
                for idx, tc in sorted(tool_calls_accumulator.items()):
                    final_tool_calls.append(tc)

                message = {"role": "assistant", "content": full_content}
                if final_tool_calls:
                    message["tool_calls"] = final_tool_calls
                
                messages.append(message)
                
                if final_tool_calls:
                    now_assistant = datetime.datetime.now().strftime("%H:%M:%S")
                    history_assistant_msg = message.copy()
                    history_assistant_msg["timestamp"] = now_assistant
                    history_assistant_msg["is_internal"] = True
                    self.history.append(history_assistant_msg)
                    
                    for tool_call in final_tool_calls:
                        function_name = tool_call["function"]["name"]
                        arguments_raw = tool_call["function"]["arguments"]
                        
                        try:
                            args_dict = json.loads(arguments_raw)
                        except json.JSONDecodeError:
                            args_dict = {}
                            
                        args_str = ", ".join(f"{k}={v}" for k, v in args_dict.items())
                        log_text = f"> Regis (Gemini) używa: {function_name}({args_str})"
                        
                        if status_callback:
                            status_callback(log_text)
                            
                        now_tool = datetime.datetime.now().strftime("%H:%M:%S")
                        self.history.append({
                            "role": "tool_log",
                            "content": log_text,
                            "timestamp": now_tool
                        })
                                
                        tool_result = tools_registry.execute_tool(function_name, args_dict)
                        
                        tool_msg = {
                            "role": "tool",
                            "name": function_name,
                            "tool_call_id": tool_call["id"],
                            "content": tool_result
                        }
                        messages.append(tool_msg)
                        
                        history_tool_msg = tool_msg.copy()
                        history_tool_msg["is_internal"] = True
                        self.history.append(history_tool_msg)
                else:
                    response_text = message.get("content", "")
                    now_assistant = datetime.datetime.now().strftime("%H:%M:%S")
                    self.history.append({"role": "assistant", "content": response_text, "timestamp": now_assistant})
                    
                    if len(self.history) > self.history_limit:
                        self.history = self.history[-self.history_limit:]

                    if final_response_callback:
                        final_response_callback(response_text)
                        
                    return response_text
                    
            except RequestException as e:
                logging.error(f"Gemini API Error: {e}")
                raise LLMConnectionError(f"Odrzucono zapytanie (HTTP Error): {e}")
