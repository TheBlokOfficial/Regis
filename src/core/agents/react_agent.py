import json
import logging
import requests
import re
import time
from requests.exceptions import RequestException
from typing import Any

from core.exceptions import LLMConnectionError
from core import config
from core.schemas import BASE_TOOLS_SCHEMA

class ReActAgent:
    """Agent wykonujący pętlę ReAct (Reasoning and Acting) dla modeli takich jak Regis."""

    def __init__(self, model_name: str, temperature: float):
        self.model_name = model_name
        self.temperature = temperature

    def _parse_tool_call_from_text(self, response_text: str) -> tuple[dict | None, str]:
        """Parsuje wywołanie narzędzia z tekstu odpowiedzi."""
        all_known_tools = [t["function"]["name"] for t in BASE_TOOLS_SCHEMA]
        
        # Metoda 1: szukaj jawnego bloku <action>...</action>
        tag_match = re.search(r'<action>\s*(.*?)\s*(?:</action>|$)', response_text, re.DOTALL)
        if tag_match:
            try:
                parsed = json.loads(tag_match.group(1))
                func_name = parsed.get("name", "")
                func_args = parsed.get("arguments", {})
                if func_name in all_known_tools:
                    cleaned = response_text[:tag_match.start()].strip()
                    cleaned = cleaned.replace("<action>", "").replace("</action>", "").strip()
                    return {"function": {"name": func_name, "arguments": func_args}}, cleaned
            except json.JSONDecodeError:
                logging.warning(f"Znaleziono blok <action>, ale JSON jest nieprawidłowy: {tag_match.group(1)[:100]}")
        
        # Metoda 2: fallback — szukaj luźnego JSONa z polem "name" pasującym do narzędzia
        stack = []
        start_idx = -1
        in_string = False
        escape_next = False
        extracted_jsons = []
        
        for i, char in enumerate(response_text):
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    if not stack:
                        start_idx = i
                    stack.append(char)
                elif char == '}':
                    if stack:
                        stack.pop()
                        if not stack:
                            json_str = response_text[start_idx:i+1]
                            try:
                                parsed = json.loads(json_str)
                                if isinstance(parsed, dict) and (parsed.get("name") in all_known_tools or parsed.get("name") in ["execute_ha_action", "execute_action"]):
                                    extracted_jsons.append((parsed, start_idx, i+1))
                            except json.JSONDecodeError:
                                pass
        
        if extracted_jsons:
            parsed, start_idx, end_idx = extracted_jsons[0]
            func_name = parsed["name"]
            func_args = parsed.get("arguments", {})
            cleaned = response_text[:start_idx].strip()
            cleaned = cleaned.replace("<action>", "").replace("</action>", "").replace("```json", "").replace("```", "").strip()
            logging.warning(f"Zastosowano fallback parsowania dla narzędzia: {func_name}")
            return {"function": {"name": func_name, "arguments": func_args}}, cleaned
        
        return None, response_text

    def generate_response(self, messages: list[dict], tools_registry, parser, on_tool_call: Any, on_thought_token: Any, on_content_token: Any, on_raw_tool_call: Any = None, on_profiler: Any = None) -> str:
        """Uruchamia pętlę decyzyjną ReAct."""
        settings = config.load_settings()
        chat_url = f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/chat"

        max_iterations = 15
        iteration_count = 0

        while iteration_count < max_iterations:
            iteration_count += 1
            parser.reset_state()
            
            payload = {
                "model": self.model_name,
                "messages": messages,
                "stream": True,
                "keep_alive": -1,
                "options": {
                    "temperature": self.temperature,
                    "num_ctx": 8192,
                    "top_p": 0.8,
                    "repeat_penalty": 1.05,
                    "num_predict": 1536,
                    "stop": ["</action>", "</action >"]
                }
            }

            try:
                inference_start = time.perf_counter()
                first_token_received = False
                response = requests.post(chat_url, json=payload, timeout=300, stream=True)
                response.raise_for_status()

                full_content = ""
                try:
                    for line in response.iter_lines():
                        if not line:
                            continue
                            
                        if not first_token_received:
                            ttft = time.perf_counter() - inference_start
                            if on_profiler:
                                on_profiler({"metric": "llm_ttft", "value": int(ttft * 1000)})
                            first_token_received = True
                            
                        chunk = json.loads(line)
                        msg_chunk = chunk.get("message", {})

                        if "content" in msg_chunk and msg_chunk["content"]:
                            piece = msg_chunk["content"]
                            full_content += piece
                            parser.feed_token(piece)
                finally:
                    if first_token_received:
                        total_inference = time.perf_counter() - inference_start
                        ttft = locals().get('ttft', 0)
                        gen_time = total_inference - ttft
                        if on_profiler:
                            on_profiler({"metric": "llm_gen", "value": int(gen_time * 1000)})

                inference_time = time.perf_counter() - inference_start
                response_text = full_content
                tool_call, cleaned_text = self._parse_tool_call_from_text(response_text)

                if tool_call:
                    # Poprawka: Odbudowujemy czysty komunikat dla modelu, unikając zepsutego formatu z fallbacku
                    func_name = tool_call["function"]["name"]
                    func_args = tool_call["function"]["arguments"]
                    call_str = json.dumps({"name": func_name, "arguments": func_args}, ensure_ascii=False)
                    
                    clean_thought = cleaned_text.strip()
                    clean_thought = clean_thought.replace("<thought>", "").replace("</thought>", "").strip()
                    
                    # Wymuszamy tag <thought> dla spójności historii
                    if clean_thought:
                        clean_response = f"<thought>\n{clean_thought}\n</thought>\n<action>{call_str}</action>"
                    else:
                        clean_response = f"<action>{call_str}</action>"
                        
                    messages.append({"role": "assistant", "content": clean_response})
                    
                    function_name = func_name
                    arguments = func_args

                    if isinstance(arguments, str):
                        try:
                             arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                             arguments = {"raw_args": arguments}
                    if not isinstance(arguments, dict):
                        arguments = {"raw_payload": str(arguments)}

                    args_str = ", ".join(f"{k}={v}" for k, v in arguments.items())
                    log_text = f"> Regis używa: {function_name}({args_str})  [{inference_time:.2f}s]"
                    if on_tool_call:
                        on_tool_call(log_text)

                    start_time = time.perf_counter()
                    tool_result = tools_registry.execute_tool(function_name, arguments)
                    elapsed_time = time.perf_counter() - start_time
                    if on_profiler:
                        on_profiler({"metric": "tools", "value": int(elapsed_time * 1000)})
                    
                    if on_tool_call:
                        on_tool_call(f"< Kontroler zwrócił: {tool_result}  [{elapsed_time:.2f}s]")

                    if on_raw_tool_call:
                        on_raw_tool_call({
                            "thought": clean_thought,
                            "name": function_name,
                            "arguments": arguments,
                            "result": tool_result
                        })

                    messages.append({"role": "user", "content": f"<tool_response>\n{tool_result}\n</tool_response>"})
                else:
                    messages.append({"role": "assistant", "content": response_text})
                    return response_text

            except RequestException as e:
                error_details = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    error_details += f" Body: {e.response.text}"
                logging.error(f"Błąd połączenia LLMEngine: {error_details}")
                raise LLMConnectionError(f"Nie udało się połączyć z usługą. {error_details}")
        
        return "Przerwano zapytanie. Przekroczono maksymalną liczbę wywołań narzędzi (timeout pętli ReAct)."
