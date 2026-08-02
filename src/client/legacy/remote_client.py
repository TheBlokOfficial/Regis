import json
import logging
import requests
from client.utils import LLMConnectionError

class RemoteClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", satellite_id: str | None = None, room: str | None = None):
        self.base_url = base_url
        self.satellite_id = satellite_id
        
        self.room = room
        if not self.room:
            try:
                from client.config import load_settings
                self.room = load_settings().get("room")
            except Exception:
                pass
                
        self.model_name = "Serwer Regis"
        self.temperature = "N/A"
        
    def clear_history(self) -> None:
        try:
            requests.post(f"{self.base_url}/v1/clear_history", timeout=5)
        except requests.RequestException as e:
            logging.error(f"Nie udało się wyczyścić historii na serwerze: {e}")
            
    def generate_response(self, prompt: str, tools_registry, on_tool_call=None, on_thought_token=None, on_content_token=None, on_routing_info=None, on_done=None, on_profiler=None) -> str:
        url = f"{self.base_url}/v1/chat/stream"
        payload = {"message": prompt, "satellite_id": self.satellite_id, "room": self.room}
        
        try:
            response = requests.post(url, json=payload, stream=True, timeout=300)
            response.raise_for_status()
            
            final_text = ""
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        event = json.loads(data_str)
                        ev_type = event.get("type")
                        content = event.get("content", "")
                        
                        if ev_type == "thought" and on_thought_token:
                            on_thought_token(content)
                        elif ev_type == "content" and on_content_token:
                            on_content_token(content)
                        elif ev_type == "tool_call_raw" and on_tool_call:
                            on_tool_call(content)
                        elif ev_type == "routing_info" and on_routing_info:
                            on_routing_info(event)
                        elif ev_type == "profiler" and on_profiler:
                            on_profiler(content)
                        elif ev_type == "done":
                            final_text = content
                            if on_done:
                                on_done(event)
                        elif ev_type == "error":
                            logging.error(f"Serwer zwrócił błąd: {content}")
                            final_text = f"Błąd serwera: {content}"
                    except json.JSONDecodeError:
                        pass
                        
            return final_text
        except requests.RequestException as e:
            raise LLMConnectionError(f"Błąd połączenia z serwerem API ({self.base_url}): {e}")

    def generate_response_from_audio(self, audio_bytes: bytes, on_stt_result=None, on_tool_call=None, on_thought_token=None, on_content_token=None, on_routing_info=None, on_done=None) -> str:
        url = f"{self.base_url}/v1/chat/audio_stream"
        
        try:
            files = {'file': ('audio.wav', audio_bytes, 'audio/wav')}
            data = {"room": self.room} if self.room else {}
            response = requests.post(url, files=files, data=data, stream=True, timeout=300)
            response.raise_for_status()
            
            final_text = ""
            for line in response.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if line.startswith("data: "):
                    data_str = line[6:]
                    try:
                        event = json.loads(data_str)
                        ev_type = event.get("type")
                        content = event.get("content", "")
                        
                        if ev_type == "stt_result" and on_stt_result:
                            on_stt_result(content)
                        elif ev_type == "thought" and on_thought_token:
                            on_thought_token(content)
                        elif ev_type == "content" and on_content_token:
                            on_content_token(content)
                        elif ev_type == "tool_call_raw" and on_tool_call:
                            on_tool_call(content)
                        elif ev_type == "done":
                            final_text = content
                        elif ev_type == "error":
                            logging.error(f"Serwer zwrócił błąd: {content}")
                            final_text = f"Błąd serwera: {content}"
                    except json.JSONDecodeError:
                        pass
                        
            return final_text
        except requests.RequestException as e:
            raise LLMConnectionError(f"Błąd połączenia z serwerem API (Audio): {e}")
