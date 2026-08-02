import json
import requests
import asyncio
from .player import AudioPlayer

class SSEClient:
    """Klient wysyłający paczkę audio do Kontrolera i procesujący odpowiedź (SSE)."""
    
    @staticmethod
    def post_and_process(url: str, wav_bytes: bytes, data: dict, event_bus, loop: asyncio.AbstractEventLoop, reset_callback):
        """Wysyła POST request i dekoduje Server-Sent Events z odpowiedzi."""
        try:
            files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
            resp = requests.post(url, files=files, data=data, stream=True, timeout=(3.0, 300.0))
            resp.raise_for_status()
            
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        SSEClient._handle_event(event, event_bus, loop)
                        if event.get("type") in ["done", "error"]:
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            loop.call_soon_threadsafe(event_bus.emit, {"type": "error", "message": f"Problem komunikacji z Kontrolerem: {e}"})
            
        loop.call_soon_threadsafe(reset_callback)

    @staticmethod
    def _handle_event(event: dict, event_bus, loop: asyncio.AbstractEventLoop):
        typ = event.get("type")
        content = event.get("content", "")
        
        if typ == "routing_info":
            loop.call_soon_threadsafe(event_bus.emit, event)
            loop.call_soon_threadsafe(event_bus.log, f"Złapano rutowanie do: {content}")
        elif typ == "stt_partial":
            loop.call_soon_threadsafe(event_bus.emit, {"type": "stt_partial", "text": content})
        elif typ == "stt_result":
            loop.call_soon_threadsafe(event_bus.emit, {"type": "stt_result", "text": content})
            loop.call_soon_threadsafe(event_bus.log, f"Transkrypcja: {content}")
        elif typ == "tool":
            loop.call_soon_threadsafe(event_bus.emit, {"type": "tool", "name": content})
            loop.call_soon_threadsafe(event_bus.log, f"Model używa narzędzia: {content}...")
        elif typ in ["thought", "content", "profiler"]:
            loop.call_soon_threadsafe(event_bus.emit, event)
        elif typ == "tts_audio":
            try:
                AudioPlayer.play_tts_audio(content)
            except Exception as e:
                loop.call_soon_threadsafe(event_bus.log, str(e))
        elif typ == "done":
            elapsed = event.get("elapsed_ms")
            loop.call_soon_threadsafe(event_bus.emit, {"type": "done", "elapsed_ms": elapsed})
            loop.call_soon_threadsafe(event_bus.log, f"Odpowiedź końcowa ({elapsed}ms).")
        elif typ == "error":
            loop.call_soon_threadsafe(event_bus.emit, {"type": "error", "message": f"Błąd: {content}"})
