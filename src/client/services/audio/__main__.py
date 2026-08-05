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
import httpx

from client import config
from client.engines.stt_engine import STTEngine
from client.engines.tts_engine import TTSEngine
from client.logger import setup_logging
from protocol.schemas import AudioConfig

setup_logging("service_audio")


class AudioService:
    """Bezportowa usługa Audio (STT + TTS) wykonywana jako podproces Sidecar."""

    def __init__(self, config_obj: AudioConfig | None = None):
        if config_obj is None:
            raw_config = os.environ.get("SERVICE_CONFIG")
            if raw_config:
                config_obj = AudioConfig.model_validate_json(raw_config)
            else:
                config_obj = AudioConfig()

        self.config = config_obj
        settings = config.load_settings()

        self.stt_model_size = config_obj.stt_model_size or settings.get("stt_model_size", "small")
        self.tts_model_name = config_obj.tts_model_name or settings.get("tts_model_name", "pl_PL-darkman-medium")
        self.internal_proxy_url = getattr(config_obj, "internal_proxy_url", "http://127.0.0.1:47831")

        self.stt_engine: STTEngine | None = None
        self.tts_engine: TTSEngine | None = None

    async def start(self):
        self.stt_engine = STTEngine(model_size=self.stt_model_size, language="pl")
        self.tts_engine = TTSEngine(model_name=self.tts_model_name)
        logging.info(f"Usługa Audio (STT={self.stt_model_size}, TTS={self.tts_model_name}) załadowana. Czekam na komendy z magistrali...")

        await self._listen_for_commands()

    async def _listen_for_commands(self):
        url = f"{self.internal_proxy_url}/internal/service_commands"
        while True:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", url) as response:
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            data_str = line[6:].strip()
                            if not data_str:
                                continue
                            try:
                                cmd_event = json.loads(data_str)
                                target_service = cmd_event.get("service")
                                if target_service != "audio":
                                    continue
                                command_type = cmd_event.get("command")
                                payload = cmd_event.get("payload", {})
                                task_id = cmd_event.get("task_id")
                                asyncio.create_task(self.handle_command(command_type, payload, task_id))
                            except Exception as e:
                                logging.error(f"Błąd dekodowania komendy Audio: {e}")
            except Exception as e:
                logging.warning(f"Utracono połączenie z magistralą Klienta. Ponawiam za 3s... ({e})")
                await asyncio.sleep(3)

    async def handle_command(self, command_type: str, payload: dict, task_id: str | None):
        if command_type == "transcribe":
            await self._process_transcribe(payload, task_id)
        elif command_type == "synthesize":
            await self._process_synthesize(payload, task_id)

    async def _process_transcribe(self, payload: dict, task_id: str | None):
        audio_b64 = payload.get("audio_b64", "")
        if not audio_b64:
            await self._send_task_event(task_id, {"error": "Brak danych audio"})
            return

        try:
            raw_wav = base64.b64decode(audio_b64)
            audio_io = io.BytesIO(raw_wav)
            text = await asyncio.to_thread(self.stt_engine.transcribe_audio_file, audio_io)
            await self._send_task_event(task_id, {"type": "stt_result", "text": text or ""})
        except Exception as e:
            logging.exception("Błąd transkrypcji STT w podprocesie")
            await self._send_task_event(task_id, {"type": "error", "content": str(e)})

    async def _process_synthesize(self, payload: dict, task_id: str | None):
        text = payload.get("text", "")
        if not text or not text.strip():
            await self._send_task_event(task_id, {"type": "tts_result", "audio_b64": ""})
            return

        try:
            b64_audio = await asyncio.to_thread(self.tts_engine.synthesize_to_base64, text)
            await self._send_task_event(task_id, {"type": "tts_result", "audio_b64": b64_audio or ""})
        except Exception as e:
            logging.exception("Błąd syntezy TTS w podprocesie")
            await self._send_task_event(task_id, {"type": "error", "content": str(e)})

    async def _send_task_event(self, task_id: str | None, event: dict):
        if not task_id:
            return
        url = f"{self.internal_proxy_url}/internal/task_event"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={"task_id": task_id, "event": event})
        except Exception as e:
            logging.warning(f"Błąd wysyłania wyników Audio do proxy: {e}")


def main():
    import json
    service = AudioService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
