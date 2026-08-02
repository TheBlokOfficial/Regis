import json
import logging
import requests
from requests.exceptions import RequestException
from typing import Any
import os

from controller.llm_backends.base import LLMBackend
from controller.exceptions import LLMConnectionError

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

class OpenRouterBackend(LLMBackend):
    def __init__(self, api_key: str, model_name: str, mode: str = "extended", temperature: float = 0.5):
        self.api_key = api_key
        self.model_name = model_name
        self.mode = mode
        self.temperature = temperature
        
    def is_available(self) -> bool:
        return bool(self.api_key and self.model_name)

    def get_provider_name(self) -> str:
        return "openrouter"

    @staticmethod
    def _accumulate_tool_call(accumulator: dict[int, dict], tc: dict, tc_pos: int) -> None:
        """Bezpiecznie dokleja lub inicjalizuje fragment wywołania narzędzia ze strumienia delta SSE."""
        idx = tc.get("index", tc_pos)
        entry = accumulator.setdefault(idx, {
            "id": tc.get("id", f"call_{idx}"),
            "type": tc.get("type", "function"),
            "function": {"name": "", "arguments": ""}
        })

        if "id" in tc and tc["id"]:
            entry["id"] = tc["id"]

        fn = tc.get("function")
        if isinstance(fn, dict):
            if name := fn.get("name"):
                entry["function"]["name"] += name
            if args := fn.get("arguments"):
                entry["function"]["arguments"] += args

    def generate_response(
        self,
        messages: list[dict],
        tools_registry: Any,
        on_tool_call: Any = None,
        on_thought_token: Any = None,
        on_content_token: Any = None,
        on_raw_tool_call: Any = None,
        on_profiler: Any = None
    ) -> str:
        if not self.is_available():
            raise LLMConnectionError("Brak klucza OPENROUTER_API_KEY lub OPENROUTER_MODEL.")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/TheBlokOfficial/Regis",
            "X-Title": "Regis Smart Home",
        }

        # Iteracyjna pętla pozwalająca na wywołanie narzędzi i zwrócenie wyniku do modelu
        max_iterations = 3 if self.mode == "basic" else 10
        iteration_count = 0

        while iteration_count < max_iterations:
            iteration_count += 1
            payload = {
                "model": self.model_name,
                "messages": messages,
                "stream": True,
                "temperature": self.temperature,
                "stream_options": {"include_usage": True}
            }
            
            if tools_registry:
                from controller.schemas_tools import get_tools_schema
                if self.mode == "basic":
                    payload["tools"] = get_tools_schema(names=["execute_action"])
                else:
                    payload["tools"] = get_tools_schema()

            try:
                import time
                t_req_start = time.time()
                t_first_token = None

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
                                if t_first_token is None:
                                    t_first_token = time.time()
                                    ttft_ms = (t_first_token - t_req_start) * 1000.0
                                    if on_profiler:
                                        on_profiler({"metric": "llm_ttft", "value": ttft_ms})
                                full_content += piece
                                if on_content_token:
                                    on_content_token(piece)
                                    
                            if "tool_calls" in delta:
                                for tc_pos, tc in enumerate(delta["tool_calls"]):
                                    self._accumulate_tool_call(tool_calls_accumulator, tc, tc_pos)
                        except json.JSONDecodeError:
                            continue

                if t_first_token is not None and on_profiler:
                    gen_ms = (time.time() - t_first_token) * 1000.0
                    on_profiler({"metric": "llm_gen", "value": gen_ms})

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
                                
                        t_tool_start = time.time()
                        if tools_registry:
                            tool_result = tools_registry.execute_tool(function_name, args_dict)
                        else:
                            tool_result = "Błąd: Brak dostępu do narzędzi."
                        t_tool_dur = (time.time() - t_tool_start) * 1000.0
                        if on_profiler:
                            on_profiler({"metric": "tools", "value": t_tool_dur})

                        if on_raw_tool_call:
                            on_raw_tool_call({
                                "thought": "",
                                "name": function_name,
                                "arguments": args_dict,
                                "result": tool_result
                            })
                        
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

        logging.warning(f"OpenRouter: przekroczono max_iterations ({max_iterations}). Przerywam pętlę.")
        return "Przerwano zapytanie. Przekroczono maksymalną liczbę wywołań narzędzi."
