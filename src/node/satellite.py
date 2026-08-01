import logging
import sys
import os
import asyncio
import json
import time
import collections
import base64

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

import sounddevice as sd
import numpy as np
import queue as _q
import threading
import requests
import wave
import io
import requests

from core import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

try:
    from openwakeword.model import Model
    from openwakeword.utils import download_models
except ImportError:
    logging.info("Brak openwakeword. Zainstaluj: pip install openwakeword")
    sys.exit(1)

# Parametry audio
SAMPLE_RATE = 16000
CHUNK_SIZE = 1600 # 100ms blok dla stabilniejszego liczenia energii (zamiast malych paczek 30ms)
SILENCE_TIMEOUT_MS = 1500 # 1.5 sekundy mowy (Speech tail) - czas czekania z przerwaniem po wejściu w ciszę
SILENCE_THRESHOLD = 300   # Próg głośności (RMS) oddzielający ciszę od głosu

class EnergyVAD:
    """Własny VAD bazujący na energii RMS (zoptymalizowany o duże bloki i wygładzanie)."""
    def __init__(self, threshold=300):
        self.threshold = threshold
        
    def is_speech(self, chunk: np.ndarray) -> bool:
        # np.ndarray to macierz w int16
        # Liczymy głośność z użyciem float32 by zapobiec overflow
        rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
        return rms >= self.threshold

class EventBus:
    """Odpowiada za komunikację z UI (Monitorem) przez eventy.

    Wysyła zdarzenia do dwóch odbiorców równolegle:
    - lokalny serwis (port 8099) — Monitor Audio
    - Kontroler (POST /api/satellite/event) — centralny Web UI
    """

    # Typy zdarzeń, które trafiają do centralnego Web UI Kontrolera.
    _CONTROLLER_PUSH_TYPES = {"state", "stt_result", "done", "error", "vad_speech", "vad_silence", "wakeword"}

    def __init__(self, service_url="http://127.0.0.1:8099",
                 controller_url: str | None = None,
                 satellite_id: str | None = None):
        self.url = service_url
        self.controller_url = controller_url
        self.satellite_id = satellite_id
        self.queue = _q.Queue()
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
    def _worker(self):
        with requests.Session() as s:
            while True:
                event = self.queue.get()
                # 1. Lokalny serwis (Monitor Audio)
                try:
                    s.post(f"{self.url}/satellite/event", json=event, timeout=0.5)
                except Exception:
                    pass
                # 2. Centralny EventBus Kontrolera (Web UI)
                if self.controller_url and event.get("type") in self._CONTROLLER_PUSH_TYPES:
                    try:
                        payload = {
                            "satellite_id": self.satellite_id or "unknown",
                            "type": event.get("type"),
                            "data": {k: v for k, v in event.items() if k != "type"},
                        }
                        s.post(
                            f"{self.controller_url}/api/satellite/event",
                            json=payload,
                            timeout=0.5,
                        )
                    except Exception:
                        pass
                self.queue.task_done()
                
    def emit(self, event: dict):
        try:
            self.queue.put_nowait(event)
        except Exception:
            pass
            
    def log(self, message: str):
        """Pomocnik rzucający logi w Monitor Audio, wyłapywane jako info."""
        self.emit({"type": "info", "message": message})


class SatelliteNode:
    def __init__(self):
        settings = config.load_settings()
        self.server_url = settings.get("server_url", settings.get("controller_url", "http://127.0.0.1:8000"))
        if self.server_url == "auto":
            from core.discovery import discover_controller
            try:
                self.server_url = discover_controller()
            except Exception:
                self.server_url = "http://127.0.0.1:8000"

        self.satellite_id = settings.get("instance_name", settings.get("satellite_id", "RTX-5070"))
        self.event_bus = EventBus(
            controller_url=self.server_url,
            satellite_id=self.satellite_id,
        )
        self.vad = EnergyVAD(threshold=SILENCE_THRESHOLD)
        self.state = "WAKEWORD" # WAKEWORD, STREAMING, RESPONDING
        
        # Bufor pre-rekordu (np. ostatnie 3 sekundy dźwięku przed wykryciem wakeword)
        # Pomaga uniknąć ucinania. Wydłużony z 1.5s do 3s, by na pewno złapać "Regis".
        self.ring_buffer = collections.deque(maxlen=30)
        
        # openwakeword model
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
            

        self.room = settings.get("room", "gabinet")
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
        logging.info("Regis Satellite (Streaming & Smart Energy VAD)")
        self.event_bus.emit({"type": "state", "state": "WAKEWORD"})
        self.event_bus.log("Satelita uruchomiona - gotowość do nasłuchu Wake Word.")
        self.stream.start()
        
        try:
            while True:
                if self.state == "WAKEWORD":
                    await self._handle_wakeword()
                elif self.state == "STREAMING":
                    await self._handle_streaming()
                elif self.state == "RESPONDING":
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            self.stream.stop()
            self.stream.close()
            
    async def _handle_wakeword(self):
        if self.oww_model is None:
            await asyncio.to_thread(input, "Naciśnij ENTER, aby rozpocząć strumieniowanie...")
            self._set_state("STREAMING")
            return
            
        chunk = await self.audio_queue.get()
        # Odłóż klatkę do bufora pre-rekordu przed jej skonsumowaniem
        self.ring_buffer.append(chunk)
        
        # Continuous VAD Tracking (użytkownik mówi / milczy przed wybudzeniem)
        is_speech = self.vad.is_speech(chunk)
        current_speech_state = "vad_speech" if is_speech else "vad_silence"
        if getattr(self, "_last_wakeword_speech_state", None) != current_speech_state:
            self.event_bus.emit({"type": current_speech_state})
            self._last_wakeword_speech_state = current_speech_state

        # VAD Bramkowanie: Jeśli panuje cisza, nie marnujmy procesora na inferencję ONNX WakeWord
        if not is_speech:
            return

        pcm16_1d = chunk[:, 0]
        prediction = self.oww_model.predict(pcm16_1d)
        
        for mdl, score in prediction.items():
            if score > 0.65:
                logging.info(f"Wybudzono! (score: {score:.2f})")
                
                # Gładki, natywny dźwięk wybudzenia (Speech On)
                if sys.platform == 'win32':
                    import winsound
                    snd_path = r"C:\Windows\Media\Speech On.wav"
                    if os.path.exists(snd_path):
                        winsound.PlaySound(snd_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    
                self.event_bus.emit({"type": "wakeword", "score": score})
                self.event_bus.emit({"type": "state", "state": "LISTENING"})
                self.event_bus.log(f"Wykryto Wake Word '{mdl}' z wynikiem: {score:.2f}! Start nagrywania...")
                # Usunięto _empty_queue aby nie ucinać pierwszych sylab!
                self._set_state("STREAMING")
                break

    async def _handle_streaming(self):
        self.event_bus.log("Słucham... (VAD śledzi dynamikę zdania)")
        
        silence_frames = 0
        max_silence_frames = max(1, int((SILENCE_TIMEOUT_MS / 1000.0) * SAMPLE_RATE / CHUNK_SIZE))
        collected_chunks = []
        last_speech_state = None
        
        # 1. Zbieramy pre-rekord
        while self.ring_buffer:
            collected_chunks.append(self.ring_buffer.popleft().tobytes())
            
        # 2. Nagrywamy dopóki nie usłyszymy ciszy
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
                    
                    if sys.platform == 'win32':
                        import winsound
                        snd_path = r"C:\Windows\Media\Speech Sleep.wav"
                        if os.path.exists(snd_path):
                            winsound.PlaySound(snd_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                    break
        except Exception as e:
            self.event_bus.log(f"Błąd nagrywania audio: {e}")
            self._reset_to_wakeword()
            return

        # 3. Tworzymy plik WAV w pamięci
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2) # 16-bit PCM = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(collected_chunks))
            
        wav_bytes = wav_io.getvalue()
        self.event_bus.log(f"Przygotowano paczkę audio ({len(wav_bytes)} bajtów). Wysyłam do Kontrolera...")
        
        # 4. Wysyłamy i odbieramy SSE w osobnym wątku (nie blokujemy asyncio)
        loop = asyncio.get_running_loop()
        url = f"{self.server_url}/v1/chat/audio_stream"
        
        def _post_and_process_sse():
            try:
                files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
                data = {}
                if hasattr(self, 'room') and self.room:
                    data["room"] = self.room
                elif hasattr(self, 'satellite_id') and self.satellite_id:
                    data["satellite_id"] = self.satellite_id
                    
                resp = requests.post(url, files=files, data=data, stream=True, timeout=(3.0, 300.0))
                resp.raise_for_status()
                
                for line in resp.iter_lines():
                    if not line:
                        continue
                    line = line.decode("utf-8")
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
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
                            elif typ == "thought":
                                loop.call_soon_threadsafe(self.event_bus.emit, event)
                            elif typ == "content":
                                loop.call_soon_threadsafe(self.event_bus.emit, event)
                            elif typ == "tts_audio":
                                try:
                                    audio_data = base64.b64decode(content)
                                    with wave.open(io.BytesIO(audio_data), 'rb') as wf:
                                        samplerate = wf.getframerate()
                                        frames = wf.readframes(wf.getnframes())
                                        audio_array = np.frombuffer(frames, dtype=np.int16)
                                        sd.play(audio_array, samplerate)
                                        sd.wait()
                                except Exception as e:
                                    loop.call_soon_threadsafe(self.event_bus.log, f"Błąd odtwarzania TTS: {e}")
                            elif typ == "profiler":
                                loop.call_soon_threadsafe(self.event_bus.emit, event)
                            elif typ == "done":
                                elapsed = event.get("elapsed_ms")
                                loop.call_soon_threadsafe(self.event_bus.emit, {"type": "done", "elapsed_ms": elapsed})
                                loop.call_soon_threadsafe(self.event_bus.log, f"Odpowiedź końcowa ({elapsed}ms).")
                                break
                            elif typ == "error":
                                loop.call_soon_threadsafe(self.event_bus.emit, {"type": "error", "message": f"Błąd: {content}"})
                                break
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                loop.call_soon_threadsafe(self.event_bus.emit, {"type": "error", "message": f"Problem komunikacji z Kontrolerem: {e}"})
                
            loop.call_soon_threadsafe(self._reset_to_wakeword)

        # Uruchamiamy wątek w tle
        await asyncio.to_thread(_post_and_process_sse)
            
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
    node = SatelliteNode()
    await node.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Satelita zamykana.")
