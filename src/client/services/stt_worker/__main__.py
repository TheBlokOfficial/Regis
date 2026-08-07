"""
Główny orkiestrator usługi STT Worker (Bezportowy Sidecar Worker dla Transkrypcji Mowy).

Usługa nie otwiera własnych portów HTTP. Podłącza się do magistrali Aplikacji Klienckiej
(internal_proxy.py) i pasywnie wykonuje komendy transkrypcji (STT).
"""
import os
import sys
import io
import base64
import asyncio
import logging

from client import config
from client.services.base import BaseService
from protocol.schemas import STTConfig, ServiceState
from client.services.stt_worker.engine import STTEngine

logging.basicConfig(level=logging.INFO, format="%(message)s")


class STTWorkerService(BaseService):
    """Bezportowa usługa STT Worker (Whisper) wykonywana jako podproces Sidecar."""

    def __init__(self, config_obj: STTConfig | None = None):
        super().__init__(service_name="stt_worker", config_class=STTConfig, config_obj=config_obj)
        settings = config.load_settings()

        self.stt_model_size = getattr(self.config, "stt_model_size", None) or settings.get("stt_model_size", "small")
        self.stt_engine: STTEngine | None = None
        self._ensure_ready_task: asyncio.Task | None = None

    async def _ensure_ready_loop(self):
        """Pętla samolecząca. Inicjalizuje silnik Whisper w osobnym wątku bez blokowania event loopa."""
        while self.state == ServiceState.INITIALIZING:
            try:
                logging.info(f"[STT Worker] Inicjalizacja silnika STT (Whisper model={self.stt_model_size})...")
                if self.stt_engine is None:
                    self.stt_engine = await asyncio.to_thread(
                        STTEngine, model_size=self.stt_model_size, language="pl"
                    )

                await self._set_state(ServiceState.READY)
                logging.info("[STT Worker] Silnik STT gotowy (READY). Czekam na komendy transkrypcji...")
                break
            except Exception as e:
                logging.error(f"[STT Worker] Błąd inicjalizacji silnika STT: {e}. Ponowienie próby za 3s...")
                await asyncio.sleep(3.0)

    def _trigger_healing(self):
        """Anuluje obecną pętlę inicjalizacyjną i uruchamia nową."""
        if self._ensure_ready_task and not self._ensure_ready_task.done():
            self._ensure_ready_task.cancel()
        self.state = ServiceState.INITIALIZING
        self._ensure_ready_task = asyncio.create_task(self._ensure_ready_loop())

    async def start(self):
        self._trigger_healing()
        await super().start()

    async def stop(self):
        if self._ensure_ready_task:
            self._ensure_ready_task.cancel()
        self.stt_engine = None
        logging.info("[STT Worker] Usługa zatrzymana.")

    async def handle_command(self, command_type: str, payload: dict, task_id: str | None):
        if self.state != ServiceState.READY:
            logging.warning(f"[STT Worker] Odrzucono zadanie ({command_type}) - worker jest {self.state.value}")
            await self.send_task_event(task_id, {
                "type": "error",
                "content": f"STT worker is currently {self.state.value}"
            })
            return

        if command_type in ("transcribe", "stt"):
            await self._process_transcribe(payload, task_id)

    async def _process_transcribe(self, payload: dict, task_id: str | None):
        audio_b64 = payload.get("audio_b64", "")
        if not audio_b64:
            await self.send_task_event(task_id, {"error": "Brak danych audio"})
            return

        await self._set_state(ServiceState.BUSY)
        try:
            raw_wav = base64.b64decode(audio_b64)
            audio_io = io.BytesIO(raw_wav)
            text = await asyncio.to_thread(self.stt_engine.transcribe_audio_file, audio_io)
            await self.send_task_event(task_id, {"type": "stt_result", "text": text or ""})
            await self._set_state(ServiceState.READY)
        except Exception as e:
            logging.exception("Błąd transkrypcji w STT Worker")
            await self.send_task_event(task_id, {"type": "error", "content": str(e)})
            self._trigger_healing()


def main():
    service = STTWorkerService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        asyncio.run(service.stop())


if __name__ == "__main__":
    main()
