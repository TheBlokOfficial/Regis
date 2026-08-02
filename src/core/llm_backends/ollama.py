import logging
import json
import time
import requests
from requests.exceptions import RequestException
from typing import Any

from core.llm_backends.base import LLMBackend
from core.exceptions import LLMConnectionError
from core import config

class OllamaBackend(LLMBackend):
    def __init__(self, model_name: str, mode: str = "extended", temperature: float = 0.1):
        self.model_name = model_name
        self.mode = mode
        self.temperature = temperature
        logging.info(f"Zainicjalizowano OllamaBackend: Model={model_name}, Mode={mode}, Temp={temperature}")

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
        settings = config.load_settings()
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/chat"

        max_iterations = 3 if self.mode == "basic" else 10
        iteration_count = 0

        while iteration_count < max_iterations:
            iteration_count += 1
            payload = {
                "model": self.model_name,
                "messages": messages,
                "stream": True,
                "options": {
                    "temperature": self.temperature
                }
            }

            if tools_registry:
                from core.schemas import get_tools_schema
                if self.mode == "basic":
                    payload["tools"] = get_tools_schema(names=["execute_action"])
                else:
                    payload["tools"] = get_tools_schema()

            try:
                t_req_start = time.time()
                t_first_token = None

                response = requests.post(url, json=payload, timeout=120, stream=True)
                if response.status_code != 200:
                    raise LLMConnectionError(f"HTTP {response.status_code}: {response.text}")

                full_content = ""
                final_tool_calls = []

                for line in response.iter_lines():
                    if not line:
                        continue
                        
                    decoded_line = line.decode('utf-8')
                    try:
                        chunk = json.loads(decoded_line)
                        msg = chunk.get("message", {})
                        
                        if "content" in msg and msg["content"]:
                            piece = msg["content"]
                            if t_first_token is None:
                                t_first_token = time.time()
                                ttft_ms = (t_first_token - t_req_start) * 1000.0
                                if on_profiler:
                                    on_profiler({"metric": "llm_ttft", "value": ttft_ms})
                            full_content += piece
                            if on_content_token:
                                on_content_token(piece)
                                
                        if "tool_calls" in msg and msg["tool_calls"]:
                            final_tool_calls = msg["tool_calls"]
                            
                        # Opcjonalnie: Ollama przesyła eval_count w ostatnim chunk (done=true)
                        if chunk.get("done") and "eval_count" in chunk:
                            pass
                    except json.JSONDecodeError:
                        continue

                if t_first_token is not None and on_profiler:
                    gen_ms = (time.time() - t_first_token) * 1000.0
                    if on_profiler:
                        on_profiler({"metric": "llm_gen", "value": gen_ms})

                message = {"role": "assistant", "content": full_content}
                if final_tool_calls:
                    message["tool_calls"] = final_tool_calls
                
                messages.append(message)
                
                if final_tool_calls:
                    for tc in final_tool_calls:
                        function_name = tc["function"]["name"]
                        arguments = tc["function"]["arguments"] # Słownik u Ollamy (w OpenRouter to string!)
                        
                        if isinstance(arguments, str):
                            try:
                                args_dict = json.loads(arguments)
                            except json.JSONDecodeError:
                                args_dict = {}
                        else:
                            args_dict = arguments
                            
                        if on_raw_tool_call:
                            on_raw_tool_call({"name": function_name, "arguments": args_dict})
                            
                        if on_tool_call:
                            on_tool_call(f"Używam narzędzia: {function_name} z argumentami: {json.dumps(args_dict, ensure_ascii=False)}")
                        
                        t_tool_start = time.time()
                        result = tools_registry.execute_tool(function_name, args_dict)
                        tool_time_ms = (time.time() - t_tool_start) * 1000.0
                        
                        if on_profiler:
                            on_profiler({"metric": "tool_exec", "value": tool_time_ms})
                        
                        messages.append({
                            "role": "tool",
                            "name": function_name,
                            "content": json.dumps(result, ensure_ascii=False)
                        })
                    # Po wykonaniu narzędzi kontynuuj pętlę
                    continue
                else:
                    # Brak narzędzi - zakończenie
                    return full_content

            except RequestException as e:
                logging.error(f"Ollama API Error: {e}")
                raise LLMConnectionError(f"Błąd komunikacji z modelem: {e}")

        logging.warning(f"Ollama: przekroczono max_iterations ({max_iterations}). Przerywam pętlę.")
        return "Przerwano zapytanie. Przekroczono maksymalną liczbę wywołań narzędzi."

    def is_available(self) -> bool:
        settings = config.load_settings()
        tags_url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/tags"
        try:
            response = requests.get(tags_url, timeout=2)
            return response.status_code == 200
        except RequestException:
            return False

    def get_provider_name(self) -> str:
        return "ollama"

    def preload_model(self) -> None:
        settings = config.load_settings()
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/generate"
        payload = {"model": self.model_name, "keep_alive": -1}
        try:
            response = requests.post(url, json=payload, timeout=(3, 120))
            response.raise_for_status()
            logging.info(f"Wstępnie załadowano model {self.model_name} do VRAM.")
        except RequestException as e:
            logging.error(f"Nie udało się połączyć z Ollamą lub załadować modelu: {e}")
            raise LLMConnectionError(f"Ollama Preload Error: {e}")

    def unload_model(self) -> None:
        settings = config.load_settings()
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/generate"
        payload = {"model": self.model_name, "keep_alive": 0}
        try:
            requests.post(url, json=payload, timeout=5)
            logging.info(f"Wysłano żądanie wyładowania modelu {self.model_name} z VRAM.")
        except Exception as e:
            logging.warning(f"Nie udało się wyładować modelu: {e}")
