import json
import requests
import asyncio
from .player import AudioPlayer


class SSEClient:
    """Klient wysyłający paczkę audio do Kontrolera i procesujący odpowiedź (SSE).

    W nowej architekturze SSE nie zawiera już tts_audio – audio jest dostarczane
    przez kanał WebSocket (komenda play_audio). SSE służy wyłącznie do przekazywania
    zdarzeń informacyjnych (transkrypcja, narzędzia, myśli modelu).
    """

    @staticmethod
    def post_and_process(url: str, wav_bytes: bytes, event_bus, loop: asyncio.AbstractEventLoop, reset_callback):
        """
        Wysyła POST request i dekoduje Server-Sent Events z odpowiedzi.
        reset_callback wywoływane jest WYŁĄCZNIE w razie błędu komunikacji –
        w normalnym przepływie powrót do nasłuchu inicjuje Kontroler przez komendę WS.
        """
        completed_normally = False
        try:
            files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
            resp = requests.post(url, files=files, stream=True, timeout=(3.0, 300.0))
            resp.raise_for_status()

            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    try:
                        event = json.loads(line[6:])
                        SSEClient._handle_event(event, event_bus, loop)
                        if event.get("type") == "done":
                            completed_normally = True
                            break
                        if event.get("type") == "error":
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            loop.call_soon_threadsafe(event_bus.emit, {"type": "error", "message": f"Problem komunikacji z Kontrolerem: {e}"})

        # Reset tylko przy błędzie – normalny reset przychodzi przez WS (start_listening)
        if not completed_normally:
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
            # tts_audio jest teraz dostarczane przez kanał WebSocket (komenda play_audio).
            # Jeśli mimo to nadejdzie przez SSE, ignorujemy – Kontroler jest źródłem prawdy.
            pass
        elif typ == "done":
            loop.call_soon_threadsafe(event_bus.emit, {"type": "done"})
        elif typ == "error":
            loop.call_soon_threadsafe(event_bus.emit, {"type": "error", "message": f"Błąd: {content}"})
