import logging
import httpx

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

    async def send_audio_payload(self, wav_bytes: bytes) -> bool:
        """Wysyła nagraną paczkę audio (WAV) do Kontrolera."""
        url = f"{self.proxy_url}/internal/audio"
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        timeout = httpx.Timeout(connect=3.0, read=300.0, write=30.0, pool=None)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(url, files=files)
                return resp.status_code == 200
        except Exception as e:
            self.event_bus.emit({"type": "error", "message": f"Problem komunikacji z Kontrolerem: {e}"})
            return False
