import json
import logging
import requests
from requests.exceptions import RequestException
from typing import Any
import os

from core.llm_backends.base import LLMBackend
from core.exceptions import LLMConnectionError

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

class OpenRouterBackend(LLMBackend):
    def __init__(self, temperature: float = 0.5):
        self.temperature = temperature
        from core import config
        # Wymuszamy załadowanie .env by mieć pewność
        config.load_settings()
        self.api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self.model_name = os.environ.get("OPENROUTER_MODEL", "")
        
    def is_available(self) -> bool:
        return bool(self.api_key and self.model_name)

    def get_provider_name(self) -> str:
        return "openrouter"

    def generate_response(
        self,
        messages: list[dict],
        tools_registry: Any,
        tier: str,
        on_tool_call: Any = None,
        on_thought_token: Any = None,
        on_content_token: Any = None,
        on_raw_tool_call: Any = None,
        on_profiler: Any = None
    ) -> str:
        if not self.is_available():
            raise LLMConnectionError("Brak klucza OPENROUTER_API_KEY lub OPENROUTER_MODEL w środowisku.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/TheBlokOfficial/Regis",
            "X-Title": "Regis Smart Home",
        }

        # Iteracyjna pętla pozwalająca na wywołanie narzędzi i zwrócenie wyniku do modelu
        while True:
            payload = {
                "model": self.model_name,
                "messages": messages,
                "stream": True,
                "temperature": self.temperature,
                "stream_options": {"include_usage": True}
            }
            
            if tools_registry:
                from core.schemas import get_tools_for_tier
                payload["tools"] = get_tools_for_tier(tier)

            try:
                response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=120, stream=True)
                if response.status_code != 200:
                    raise LLMConnectionError(f"HTTP {response.status_code}: {response.text}")

                full_content = ""
                tool_calls_accumulator = {} 
                usage_stats = None

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
                            if "usage" in chunk and chunk["usage"]:
                                usage_stats = chunk["usage"]
                                
                            if not chunk.get("choices"):
                                continue
                            delta = chunk["choices"][0].get("delta", {})
                            
                            if "content" in delta and delta["content"]:
                                piece = delta["content"]
                                full_content += piece
                                if on_content_token:
                                    on_content_token(piece)
                                    
                            if "tool_calls" in delta:
                                for tc_pos, tc in enumerate(delta["tool_calls"]):
                                    idx = tc.get("index", tc_pos)
                                    if idx not in tool_calls_accumulator:
                                        tool_calls_accumulator[idx] = tc.copy()
                                        if "id" not in tool_calls_accumulator[idx]:
                                            tool_calls_accumulator[idx]["id"] = f"call_{idx}"
                                        if "type" not in tool_calls_accumulator[idx]:
                                            tool_calls_accumulator[idx]["type"] = "function"
                                        if "function" not in tool_calls_accumulator[idx]:
                                            tool_calls_accumulator[idx]["function"] = {"name": "", "arguments": ""}
                                        else:
                                            tool_calls_accumulator[idx]["function"] = tc["function"].copy()
                                            if "name" not in tool_calls_accumulator[idx]["function"]:
                                                tool_calls_accumulator[idx]["function"]["name"] = ""
                                            if "arguments" not in tool_calls_accumulator[idx]["function"]:
                                                tool_calls_accumulator[idx]["function"]["arguments"] = ""
                                    else:
                                        if "function" in tc:
                                            if "name" in tc["function"] and tc["function"]["name"]:
                                                tool_calls_accumulator[idx]["function"]["name"] += tc["function"]["name"]
                                            if "arguments" in tc["function"] and tc["function"]["arguments"]:
                                                tool_calls_accumulator[idx]["function"]["arguments"] += tc["function"]["arguments"]
                                        
                        except json.JSONDecodeError:
                            continue

                if usage_stats:
                    logging.debug(f"Zużycie tokenów OpenRouter: {usage_stats}")

                final_tool_calls = []
                for idx, tc in sorted(tool_calls_accumulator.items()):
                    final_tool_calls.append(tc)

                message = {"role": "assistant", "content": full_content}
                if final_tool_calls:
                    message["tool_calls"] = final_tool_calls
                
                messages.append(message)
                
                if final_tool_calls:
                    for tool_call in final_tool_calls:
                        function_name = tool_call["function"]["name"]
                        arguments_raw = tool_call["function"]["arguments"]
                        
                        try:
                            args_dict = json.loads(arguments_raw)
                        except json.JSONDecodeError:
                            args_dict = {}
                            
                        args_str = ", ".join(f"{k}={v}" for k, v in args_dict.items())
                        log_text = f"> Regis (OpenRouter) używa: {function_name}({args_str})"
                        
                        if on_tool_call:
                            on_tool_call(log_text)
                                
                        if tools_registry:
                            tool_result = tools_registry.execute_tool(function_name, args_dict)
                        else:
                            tool_result = "Błąd: Brak dostępu do narzędzi."
                        
                        tool_msg = {
                            "role": "tool",
                            "name": function_name,
                            "tool_call_id": tool_call["id"],
                            "content": tool_result
                        }
                        messages.append(tool_msg)
                else:
                    return full_content
                    
            except RequestException as e:
                logging.error(f"OpenRouter API Error: {e}")
                raise LLMConnectionError(f"Odrzucono zapytanie (HTTP Error): {e}")
