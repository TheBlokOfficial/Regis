import logging
import json
import time
import httpx
from typing import Any, AsyncGenerator

from node.llm_backends.base import LLMBackend
from node.utils import LLMConnectionError
from node import config

class OllamaBackend(LLMBackend):
    def __init__(self, model_name: str, mode: str = "extended", temperature: float = 0.1):
        self.model_name = model_name
        self.mode = mode
        self.temperature = temperature
        logging.info(f"Zainicjalizowano OllamaBackend: Model={model_name}, Mode={mode}, Temp={temperature}")

    async def generate_stream(
        self,
        messages: list[dict],
        tools_registry: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        
        settings = config.load_settings()
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/chat"

        max_iterations = 3 if self.mode == "basic" else 10
        iteration_count = 0

        async with httpx.AsyncClient(timeout=120.0) as client:
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

                    async with client.stream("POST", url, json=payload) as response:
                        if response.status_code != 200:
                            err_text = await response.aread()
                            raise LLMConnectionError(f"HTTP {response.status_code}: {err_text.decode('utf-8')}")

                        full_content = ""
                        final_tool_calls = []

                        async for line in response.aiter_lines():
                            if not line:
                                continue
                                
                            try:
                                chunk = json.loads(line)
                                msg = chunk.get("message", {})
                                
                                if "content" in msg and msg["content"]:
                                    piece = msg["content"]
                                    if t_first_token is None:
                                        t_first_token = time.time()
                                        ttft_ms = (t_first_token - t_req_start) * 1000.0
                                        yield {"type": "profiler", "content": {"metric": "llm_ttft", "value": ttft_ms}}
                                        
                                    full_content += piece
                                    yield {"type": "content", "content": piece}
                                        
                                if "tool_calls" in msg and msg["tool_calls"]:
                                    final_tool_calls = msg["tool_calls"]
                                    
                            except json.JSONDecodeError:
                                continue

                    if t_first_token is not None:
                        gen_ms = (time.time() - t_first_token) * 1000.0
                        yield {"type": "profiler", "content": {"metric": "llm_gen", "value": gen_ms}}

                    message = {"role": "assistant", "content": full_content}
                    if final_tool_calls:
                        message["tool_calls"] = final_tool_calls
                    
                    messages.append(message)
                    
                    if final_tool_calls:
                        for tc in final_tool_calls:
                            function_name = tc["function"]["name"]
                            arguments = tc["function"]["arguments"]
                            
                            if isinstance(arguments, str):
                                try:
                                    args_dict = json.loads(arguments)
                                except json.JSONDecodeError:
                                    args_dict = {}
                            else:
                                args_dict = arguments
                                
                            yield {"type": "tool_dict", "content": {"name": function_name, "arguments": args_dict}}
                            yield {"type": "tool_call_raw", "content": f"Używam narzędzia: {function_name} z argumentami: {json.dumps(args_dict, ensure_ascii=False)}"}
                            
                            t_tool_start = time.time()
                            # Weryfikacja: execute_tool w rejestrze narzędzi po stronie Węzła zazwyczaj jest synchroniczne (requests.post),
                            # ale z racji małych opóźnień możemy to znieść. W idealnym świecie remote_tools_registry też by było async.
                            # Użyjemy asyncio.to_thread by nie blokować pętli zdarzeń, jeśli to blokujący requests
                            import asyncio
                            result = await asyncio.to_thread(tools_registry.execute_tool, function_name, args_dict)
                            tool_time_ms = (time.time() - t_tool_start) * 1000.0
                            
                            yield {"type": "profiler", "content": {"metric": "tool_exec", "value": tool_time_ms}}
                            
                            messages.append({
                                "role": "tool",
                                "name": function_name,
                                "content": json.dumps(result, ensure_ascii=False)
                            })
                        # Po wykonaniu narzędzi kontynuuj pętlę
                        continue
                    else:
                        # Brak narzędzi - zakończenie
                        yield {"type": "done", "content": full_content}
                        return

                except httpx.RequestError as e:
                    logging.error(f"Ollama API Error: {e}")
                    raise LLMConnectionError(f"Błąd komunikacji z modelem: {e}")

            logging.warning(f"Ollama: przekroczono max_iterations ({max_iterations}). Przerywam pętlę.")
            yield {"type": "error", "content": "Przerwano zapytanie. Przekroczono maksymalną liczbę wywołań narzędzi."}

    async def is_available(self) -> bool:
        settings = config.load_settings()
        tags_url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(tags_url)
                return response.status_code == 200
        except httpx.RequestError:
            return False

    def get_provider_name(self) -> str:
        return "ollama"

    async def preload_model(self) -> None:
        settings = config.load_settings()
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/generate"
        payload = {"model": self.model_name, "keep_alive": -1}
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
            logging.info(f"Wstępnie załadowano model {self.model_name} do VRAM.")
        except httpx.RequestError as e:
            logging.error(f"Nie udało się połączyć z Ollamą lub załadować modelu: {e}")
            raise LLMConnectionError(f"Ollama Preload Error: {e}")

    async def unload_model(self) -> None:
        settings = config.load_settings()
        url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/generate"
        payload = {"model": self.model_name, "keep_alive": 0}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json=payload)
            logging.info(f"Wysłano żądanie wyładowania modelu {self.model_name} z VRAM.")
        except Exception as e:
            logging.warning(f"Nie udało się wyładować modelu: {e}")
