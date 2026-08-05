import asyncio
import collections
import io
import wave
import sounddevice as sd
from typing import Callable, List
from .vad import EnergyVAD
from ..event_bus import EventBus

SAMPLE_RATE = 16000
CHUNK_SIZE = 1600
SILENCE_TIMEOUT_MS = 700

class AudioStreamManager:
    """Zarządza strumieniem audio z mikrofonu, buforem kołowym i pakowaniem nagrań do formatu WAV."""

    def __init__(self):
        self.ring_buffer = collections.deque(maxlen=30)
        self.audio_queue = asyncio.Queue()
        self.stream = None
        self.loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def is_ready(self) -> bool:
        return self.stream is not None

    def _audio_callback(self, indata, frames, time_info, status):
        try:
            if self.loop:
                self.loop.call_soon_threadsafe(self.audio_queue.put_nowait, indata.copy())
        except Exception:
            pass

    def start_stream(self):
        if self.stream is not None:
            return
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype='int16',
            blocksize=CHUNK_SIZE, callback=self._audio_callback
        )
        self.stream.start()

    def stop_stream(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def empty_queue(self):
        while not self.audio_queue.empty():
            self.audio_queue.get_nowait()

    async def get_chunk(self):
        return await self.audio_queue.get()

    async def record_until_silence(self, vad: EnergyVAD, event_bus: EventBus, get_state_func: Callable[[], str]) -> List[bytes]:
        silence_frames = 0
        max_silence_frames = max(1, int((SILENCE_TIMEOUT_MS / 1000.0) * SAMPLE_RATE / CHUNK_SIZE))
        collected_chunks = []
        last_speech_state = None

        while self.ring_buffer:
            collected_chunks.append(self.ring_buffer.popleft().tobytes())

        while get_state_func() == "STREAMING":
            chunk = await self.audio_queue.get()
            is_speech = vad.is_speech(chunk)
            collected_chunks.append(chunk.tobytes())

            current_speech_state = "vad_speech" if is_speech else "vad_silence"
            if current_speech_state != last_speech_state:
                event_bus.emit({"type": current_speech_state})
                last_speech_state = current_speech_state

            silence_frames = 0 if is_speech else silence_frames + 1

            if silence_frames > max_silence_frames:
                event_bus.emit({"type": "vad_silence"})
                event_bus.log(f"Wykryto {SILENCE_TIMEOUT_MS}ms ciszy. Koniec nagrywania.")
                break
                
        return collected_chunks

    @staticmethod
    def create_wav_payload(collected_chunks: List[bytes]) -> bytes:
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(b''.join(collected_chunks))
        return wav_io.getvalue()
