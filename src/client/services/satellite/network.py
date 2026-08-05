import json
import asyncio
import httpx
import requests
import logging

from typing import TYPE_CHECKING, Callable
if TYPE_CHECKING:
    from protocol.schemas import ServiceCommand

from .audio.player import AudioPlayer

class SatelliteAPIClient:
    """Klient API dla komunikacji satelity z Proxy/Kontrolerem."""
    
    def __init__(self, proxy_url: str, event_bus):
        self.proxy_url = proxy_url
        self.event_bus = event_bus

    async def check_wake_permission(self) -> bool:
        """Pyta Kontrolera, czy satelita ma pozwolenie na rozpoczęcie nagrywania."""
        wake_url = f"{self.proxy_url}/internal/wake_check"
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                resp = await client.post(wake_url)
                return resp.status_code == 200 and resp.json().get("permitted", False)
        except Exception as e:
            logging.warning(f"Błąd połączenia z proxy (wake_check): {e}")
            return False

    async def report_audio_complete(self):
        """Zgłasza Kontrolerowi, że odtwarzanie audio (TTS) dobiegło końca."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                await c.post(f"{self.proxy_url}/internal/audio_complete")
        except Exception as e:
            self.event_bus.log(f"Błąd zgłoszenia audio_complete: {e}")

    async def listen_for_commands(self, handlers: dict["ServiceCommand", Callable]):
        """Nasłuchuje SSE od Kontrolera w pętli z reconnectem i przekazuje komendy do odpowiednich handlerów."""
        from protocol.schemas import ServiceCommand
        
        cmd_url = f"{self.proxy_url}/internal/service_commands"
        while True:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", cmd_url) as response:
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            try:
                                cmd_data = json.loads(line[6:])
                                command_str = cmd_data.get("command")
                                
                                try:
                                    cmd_type = ServiceCommand(command_str)
                                    handler = handlers.get(cmd_type)
                                    if handler:
                                        if asyncio.iscoroutinefunction(handler):
                                            await handler(cmd_data)
                                        else:
                                            handler(cmd_data)
                                except ValueError:
                                    pass # Komenda nierozpoznana przez Enum ServiceCommand

                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                self.event_bus.log(f"Utracono połączenie z kanałem komend. Ponawiam za 3s... ({e})")
                await asyncio.sleep(3)

    def post_audio_and_process_sse(self, wav_bytes: bytes, loop: asyncio.AbstractEventLoop):
        """Wysyła POST request i dekoduje Server-Sent Events z odpowiedzi (synchronicznie w wątku)."""
        url = f"{self.proxy_url}/internal/audio"
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
                        self._handle_sse_event(event, loop)
                        if event.get("type") in ("done", "error"):
                            break
                    except json.JSONDecodeError:
                        pass
        except Exception as e:
            loop.call_soon_threadsafe(self.event_bus.emit, {"type": "error", "message": f"Problem komunikacji z Kontrolerem: {e}"})

    def _handle_sse_event(self, event: dict, loop: asyncio.AbstractEventLoop):
        typ = event.get("type")
        content = event.get("content", "")

        if typ == "routing_info":
            loop.call_soon_threadsafe(self.event_bus.emit, event)
            loop.call_soon_threadsafe(self.event_bus.log, f"Złapano rutowanie do: {content}")
        elif typ == "stt_partial":
            loop.call_soon_threadsafe(self.event_bus.emit, {"type": "stt_partial", "text": content})
        elif typ == "stt_result":
            loop.call_soon_threadsafe(self.event_bus.emit, {"type": "stt_result", "text": content})
            loop.call_soon_threadsafe(self.event_bus.log, f"Transkrypcja: {content}")
        elif typ == "tool":
            loop.call_soon_threadsafe(self.event_bus.emit, {"type": "tool", "name": content})
            loop.call_soon_threadsafe(self.event_bus.log, f"Model używa narzędzia: {content}...")
        elif typ in ["thought", "content", "profiler"]:
            loop.call_soon_threadsafe(self.event_bus.emit, event)
        elif typ == "tts_audio":
            pass
        elif typ == "done":
            loop.call_soon_threadsafe(self.event_bus.emit, {"type": "done"})
        elif typ == "error":
            loop.call_soon_threadsafe(self.event_bus.emit, {"type": "error", "message": f"Błąd: {content}"})
