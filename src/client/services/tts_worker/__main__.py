"""
Główny orkiestrator usługi TTS Worker (Bezportowy Sidecar Worker dla Syntezy Mowy).

Usługa nie otwiera własnych portów HTTP. Podłącza się do magistrali Aplikacji Klienckiej
(internal_proxy.py) i pasywnie wykonuje komendy syntezy (TTS).
"""
import os
import sys
import io
import base64
import asyncio
import logging

from client import config
from client.services.base import BaseService
from protocol.schemas import TTSConfig, ServiceState
from client.services.tts_worker.engine import TTSEngine

logging.basicConfig(level=logging.INFO, format="%(message)s")


class TTSWorkerService(BaseService):
    """Bezportowa usługa TTS Worker (Piper) wykonywana jako podproces Sidecar."""

    def __init__(self, config_obj: TTSConfig | None = None):
        super().__init__(service_name="tts_worker", config_class=TTSConfig, config_obj=config_obj)
        settings = config.load_settings()

        self.tts_model_name = getattr(self.config, "tts_model_name", None) or settings.get("tts_model_name", "pl_PL-darkman-medium")
        self.tts_engine: TTSEngine | None = None
        self._ensure_ready_task: asyncio.Task | None = None

    async def _ensure_ready_loop(self):
        """Pętla samolecząca. Pobiera/inicjalizuje silnik Piper w osobnym wątku bez blokowania event loopa."""
        while self.state == ServiceState.INITIALIZING:
            try:
                logging.info(f"[TTS Worker] Inicjalizacja silnika TTS (Piper model={self.tts_model_name})...")
                if self.tts_engine is None:
                    self.tts_engine = await asyncio.to_thread(
                        TTSEngine, model_name=self.tts_model_name
                    )

                if self.tts_engine.voice is not None:
                    await self._set_state(ServiceState.READY)
                    logging.info("[TTS Worker] Silnik TTS gotowy (READY). Czekam na komendy syntezy...")
                    break
                else:
                    logging.warning("[TTS Worker] Silnik TTS nie jest załadowany. Ponowienie próby za 3s...")
            except Exception as e:
                logging.error(f"[TTS Worker] Błąd inicjalizacji silnika TTS: {e}. Ponowienie próby za 3s...")
                
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
        self.tts_engine = None
        logging.info("[TTS Worker] Usługa zatrzymana.")

    async def handle_command(self, command_type: str, payload: dict, task_id: str | None):
        if self.state != ServiceState.READY:
            logging.warning(f"[TTS Worker] Odrzucono zadanie ({command_type}) - worker jest {self.state.value}")
            await self.send_task_event(task_id, {
                "type": "error",
                "content": f"TTS worker is currently {self.state.value}"
            })
            return

        if command_type in ("synthesize", "tts"):
            await self._process_synthesize(payload, task_id)

    async def _process_synthesize(self, payload: dict, task_id: str | None):
        text = payload.get("text", "")
        if not text or not text.strip():
            await self.send_task_event(task_id, {"type": "tts_result", "audio_b64": ""})
            return

        await self._set_state(ServiceState.BUSY)
        try:
            b64_audio = await asyncio.to_thread(self.tts_engine.synthesize_to_base64, text)
            await self.send_task_event(task_id, {"type": "tts_result", "audio_b64": b64_audio or ""})
            await self._set_state(ServiceState.READY)
        except Exception as e:
            logging.exception("Błąd syntezy w TTS Worker")
            await self.send_task_event(task_id, {"type": "error", "content": str(e)})
            self._trigger_healing()


def main():
    service = TTSWorkerService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        asyncio.run(service.stop())


if __name__ == "__main__":
    main()
