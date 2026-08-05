import logging
import json
import time
import httpx
from typing import Any, AsyncGenerator

from client.llm_backends.base import LLMBackend
from client.utils import LLMConnectionError
from client import config

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
                    from controller.schemas_tools import get_tools_schema
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

    async def _ensure_model_exists(self, client: httpx.AsyncClient, ollama_url: str) -> None:
        """Sprawdza czy model jest obecny, jeśli nie, próbuje go pobrać."""
        try:
            tags_resp = await client.get(f"{ollama_url}/api/tags")
            tags_resp.raise_for_status()
            models = [m.get("name") for m in tags_resp.json().get("models", [])]
            
            if not any(self.model_name in m or m in self.model_name for m in models):
                logging.info(f"[Ollama Pull] Rozpoczynam pobieranie brakującego modelu '{self.model_name}'...")
                pull_resp = await client.post(
                    f"{ollama_url}/api/pull", 
                    json={"name": self.model_name}, 
                    timeout=600.0
                )
                pull_resp.raise_for_status()
                logging.info(f"[Ollama Pull] Model '{self.model_name}' pobrany pomyślnie.")
        except Exception as e:
            logging.error(f"[Ollama] Błąd weryfikacji/pobierania modelu: {e}")
            raise LLMConnectionError(f"Nie udało się zweryfikować lub pobrać modelu: {e}")

    async def preload_model(self) -> None:
        settings = config.load_settings()
        ollama_url = settings.get('ollama_url', 'http://127.0.0.1:11434')
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                await self._ensure_model_exists(client, ollama_url)
                
                url = f"{ollama_url}/api/generate"
                payload = {"model": self.model_name, "keep_alive": -1}
                
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
