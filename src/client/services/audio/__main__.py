"""
Główny orkiestrator usługi Audio (Bezportowy Sidecar Worker dla STT i TTS).

Usługa nie otwiera własnych portów HTTP. Podłącza się do magistrali Aplikacji Klienckiej
(internal_proxy.py) i pasywnie wykonuje komendy transkrypcji (STT) oraz syntezy (TTS).
"""
import os
import sys
import io
import base64
import asyncio
import logging

from client import config
from client.engines.stt_engine import STTEngine
from client.engines.tts_engine import TTSEngine
from protocol.schemas import AudioConfig
from client.services.base import BaseService
logging.basicConfig(level=logging.INFO, format="%(message)s")


class AudioService(BaseService):
    """Bezportowa usługa Audio (STT + TTS) wykonywana jako podproces Sidecar."""

    def __init__(self, config_obj: AudioConfig | None = None):
        super().__init__(service_name="audio", config_class=AudioConfig, config_obj=config_obj)
        settings = config.load_settings()

        self.stt_model_size = self.config.stt_model_size or settings.get("stt_model_size", "small")
        self.tts_model_name = self.config.tts_model_name or settings.get("tts_model_name", "pl_PL-darkman-medium")

        self.stt_engine: STTEngine | None = None
        self.tts_engine: TTSEngine | None = None

    async def start(self):
        self.stt_engine = STTEngine(model_size=self.stt_model_size, language="pl")
        self.tts_engine = TTSEngine(model_name=self.tts_model_name)
        logging.info(f"Usługa Audio (STT={self.stt_model_size}, TTS={self.tts_model_name}) załadowana. Czekam na komendy z magistrali...")

        await super().start()

    async def handle_command(self, command_type: str, payload: dict, task_id: str | None):
        if command_type == "transcribe":
            await self._process_transcribe(payload, task_id)
        elif command_type == "synthesize":
            await self._process_synthesize(payload, task_id)

    async def _process_transcribe(self, payload: dict, task_id: str | None):
        audio_b64 = payload.get("audio_b64", "")
        if not audio_b64:
            await self.send_task_event(task_id, {"error": "Brak danych audio"})
            return

        try:
            raw_wav = base64.b64decode(audio_b64)
            audio_io = io.BytesIO(raw_wav)
            text = await asyncio.to_thread(self.stt_engine.transcribe_audio_file, audio_io)
            await self.send_task_event(task_id, {"type": "stt_result", "text": text or ""})
        except Exception as e:
            logging.exception("Błąd transkrypcji STT w podprocesie")
            await self.send_task_event(task_id, {"type": "error", "content": str(e)})

    async def _process_synthesize(self, payload: dict, task_id: str | None):
        text = payload.get("text", "")
        if not text or not text.strip():
            await self.send_task_event(task_id, {"type": "tts_result", "audio_b64": ""})
            return

        try:
            b64_audio = await asyncio.to_thread(self.tts_engine.synthesize_to_base64, text)
            await self.send_task_event(task_id, {"type": "tts_result", "audio_b64": b64_audio or ""})
        except Exception as e:
            logging.exception("Błąd syntezy TTS w podprocesie")
            await self.send_task_event(task_id, {"type": "error", "content": str(e)})


def main():
    service = AudioService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
