import os
import sys
import json
import logging
import asyncio
import collections
import wave
import io
import sounddevice as sd
import httpx

from .vad import EnergyVAD
from .event_bus import EventBus
from .player import AudioPlayer
from .sse_client import SSEClient

try:
    from openwakeword.model import Model
    from openwakeword.utils import download_models
except ImportError:
    logging.info("Brak openwakeword. Zainstaluj: pip install openwakeword")
    sys.exit(1)

SAMPLE_RATE = 16000
CHUNK_SIZE = 1600
SILENCE_TIMEOUT_MS = 700
SILENCE_THRESHOLD = 150


class SatelliteService:
    """Główny orkiestrator Satelity z maszyną stanów (WAKEWORD, STREAMING, RESPONDING).

    Satelita jest czystym wykonawcą komend – nie zawiera logiki biznesowej decydującej
    o kolejności operacji. Kontroler decyduje kiedy odtwarzać audio i kiedy wrócić
    do nasłuchu Wake Word.
    """

    def __init__(self, config=None):
        from protocol.schemas import SatelliteConfig
        if config is None:
            raw_config = os.environ.get("SERVICE_CONFIG")
            if raw_config:
                config = SatelliteConfig.model_validate_json(raw_config)
            else:
                config = SatelliteConfig()

        self.config = config
        self.internal_proxy_url = config.internal_proxy_url

        self.event_bus = EventBus(satellite_id="satellite_proxy")

        self.vad = EnergyVAD(threshold=config.wakeword_threshold * 230 if config.wakeword_threshold < 1.0 else SILENCE_THRESHOLD)
        self.state = "WAKEWORD"
        self.ring_buffer = collections.deque(maxlen=30)

        model_path = os.path.abspath(os.path.join("data", "models", "wakeword.onnx"))
        if not os.path.exists(model_path):
            logging.info(f"Brak modelu {model_path}. Działanie awaryjne.")
            self.oww_model = None
        else:
            try:
                download_models()
            except Exception:
                pass
            self.oww_model = Model(wakeword_models=[model_path], inference_framework="onnx")

        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='int16',
            blocksize=CHUNK_SIZE, callback=self._audio_callback
        )

    def _audio_callback(self, indata, frames, time_info, status):
        try:
            if hasattr(self, 'loop') and hasattr(self, 'audio_queue'):
                self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, indata.copy())
        except Exception:
            pass

    async def run(self):
        self.loop = asyncio.get_running_loop()
        self.audio_queue = asyncio.Queue()
        logging.info("Regis Satellite Service (Streaming & Smart Energy VAD)")
        self.event_bus.emit({"type": "state", "state": "WAKEWORD"})
        self.event_bus.log("Satelita uruchomiona - gotowość do nasłuchu Wake Word.")
        self.stream.start()

        # Uruchom odbiornik komend od Kontrolera jako niezależny task asyncio
        asyncio.create_task(self._listen_for_commands())

        try:
            while True:
                if self.state == "WAKEWORD":
                    await self._handle_wakeword()
                elif self.state == "STREAMING":
                    await self._handle_streaming()
                elif self.state == "RESPONDING":
                    await asyncio.sleep(0.1)  # Czekamy na komendę start_listening od Kontrolera
        except asyncio.CancelledError:
            pass
        finally:
            self.stream.stop()
            self.stream.close()

    async def _listen_for_commands(self):
        """
        Nasłuchuje na komendy od Kontrolera przez SSE z Internal Proxy.
        Satelita jest czystym wykonawcą: reaguje na play_audio i start_listening.
        Pętla z automatycznym reconnect.
        """
        cmd_url = f"{self.internal_proxy_url}/internal/service_commands"
        while True:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", cmd_url) as response:
                        async for line in response.aiter_lines():
                            if not line.startswith("data: "):
                                continue
                            try:
                                cmd = json.loads(line[6:])
                                command = cmd.get("command")

                                if command == "play_audio":
                                    audio_b64 = cmd.get("audio_b64", "")
                                    self.event_bus.log("Odtwarzam odpowiedź lektora...")
                                    try:
                                        await asyncio.to_thread(AudioPlayer.play_tts_audio, audio_b64)
                                    except Exception as e:
                                        self.event_bus.log(f"Błąd odtwarzania TTS: {e}")
                                    # Poinformuj Kontrolera że skończyliśmy – to on zdecyduje co dalej
                                    try:
                                        async with httpx.AsyncClient(timeout=5.0) as c:
                                            await c.post(f"{self.internal_proxy_url}/internal/audio_complete")
                                    except Exception as e:
                                        self.event_bus.log(f"Błąd zgłoszenia audio_complete: {e}")

                                elif command == "start_listening":
                                    # Kontroler podjął decyzję – wracamy do nasłuchu
                                    self._reset_to_wakeword()

                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                self.event_bus.log(f"Utracono połączenie z kanałem komend. Ponawiam za 3s... ({e})")
                await asyncio.sleep(3)

    async def _handle_wakeword(self):
        if self.oww_model is None:
            await asyncio.to_thread(input, "Naciśnij ENTER, aby rozpocząć strumieniowanie...")
            self._set_state("STREAMING")
            return

        chunk = await self.audio_queue.get()
        self.ring_buffer.append(chunk)

        is_speech = self.vad.is_speech(chunk)
        current_speech_state = "vad_speech" if is_speech else "vad_silence"
        if getattr(self, "_last_wakeword_speech_state", None) != current_speech_state:
            self.event_bus.emit({"type": current_speech_state})
            if current_speech_state == "vad_speech":
                for pre_chunk in list(self.ring_buffer):
                    self.oww_model.predict(pre_chunk[:, 0])
            self._last_wakeword_speech_state = current_speech_state

        if not is_speech:
            return

        pcm16_1d = chunk[:, 0]
        prediction = self.oww_model.predict(pcm16_1d)

        for mdl, score in prediction.items():
            if score > 0.65:
                self.event_bus.emit({"type": "wakeword", "score": score})
                self.event_bus.log(f"Wykryto Wake Word '{mdl}' z wynikiem: {score:.2f}! Sprawdzam dostępność Kontrolera...")

                wake_url = f"{self.internal_proxy_url}/internal/wake_check"
                try:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        resp = await client.post(wake_url)
                        permitted = resp.status_code == 200 and resp.json().get("permitted", False)
                except Exception as e:
                    logging.warning(f"Błąd połączenia z proxy: {e}")
                    permitted = False

                if permitted:
                    AudioPlayer.play_system_sound("Speech On")
                    self.event_bus.emit({"type": "state", "state": "LISTENING"})
                    self.event_bus.log("Start nagrywania...")
                    self._empty_queue()
                    self._set_state("STREAMING")
                else:
                    AudioPlayer.play_system_sound("Speech Off")
                    self.event_bus.log("Odmowa nagrywania (Brak workerów lub błąd komunikacji).")

                break

    async def _handle_streaming(self):
        self.event_bus.log("Słucham... (VAD śledzi dynamikę zdania)")

        silence_frames = 0
        max_silence_frames = max(1, int((SILENCE_TIMEOUT_MS / 1000.0) * SAMPLE_RATE / CHUNK_SIZE))
        collected_chunks = []
        last_speech_state = None

        while self.ring_buffer:
            collected_chunks.append(self.ring_buffer.popleft().tobytes())

        try:
            while self.state == "STREAMING":
                chunk = await self.audio_queue.get()
                is_speech = self.vad.is_speech(chunk)
                collected_chunks.append(chunk.tobytes())

                current_speech_state = "vad_speech" if is_speech else "vad_silence"
                if current_speech_state != last_speech_state:
                    self.event_bus.emit({"type": current_speech_state})
                    last_speech_state = current_speech_state

                if not is_speech:
                    silence_frames += 1
                else:
                    silence_frames = 0

                if silence_frames > max_silence_frames:
                    self.event_bus.emit({"type": "vad_silence"})
                    self.event_bus.log(f"Wykryto {SILENCE_TIMEOUT_MS}ms ciszy. Koniec nagrywania.")
                    self._set_state("RESPONDING")
                    self.event_bus.emit({"type": "state", "state": "RESPONDING"})

                    AudioPlayer.play_system_sound("Speech Sleep")
                    break
        except Exception as e:
            self.event_bus.log(f"Błąd nagrywania audio: {e}")
            self._reset_to_wakeword()
            return

        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(collected_chunks))

        wav_bytes = wav_io.getvalue()
        self.event_bus.log(f"Przygotowano paczkę audio ({len(wav_bytes)} bajtów). Wysyłam do Kontrolera...")

        url = f"{self.internal_proxy_url}/internal/audio"

        # reset_callback wywoływany WYŁĄCZNIE przy błędzie – normalny reset przychodzi
        # przez kanał WS (komenda start_listening od Kontrolera, po audio_complete od nas).
        await asyncio.to_thread(
            SSEClient.post_and_process,
            url, wav_bytes, self.event_bus, self.loop, self._reset_to_wakeword
        )

    def _reset_to_wakeword(self):
        self._empty_queue()
        if self.oww_model is not None:
            self.oww_model.reset()
        self._set_state("WAKEWORD")
        self.event_bus.emit({"type": "state", "state": "WAKEWORD"})
        self.event_bus.log("Cykl odpowiedzi zakończony. Powrót do nasłuchu Wake Word.")

    def _set_state(self, new_state):
        self.state = new_state

    def _empty_queue(self):
        while not self.audio_queue.empty():
            self.audio_queue.get_nowait()


async def main():
    import argparse
    from protocol.schemas import SatelliteConfig

    parser = argparse.ArgumentParser(description="Regis Satellite Service")
    parser.add_argument("--internal-proxy-url", type=str, default=None, help="Adres serwera proxy (domyślnie http://127.0.0.1:47831)")
    args = parser.parse_known_args()[0]

    raw_config = os.environ.get("SERVICE_CONFIG")
    if raw_config:
        config = SatelliteConfig.model_validate_json(raw_config)
    else:
        config = SatelliteConfig()

    if args.internal_proxy_url:
        config.internal_proxy_url = args.internal_proxy_url

    service = SatelliteService(config=config)
    await service.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Satelita zamykana.")
