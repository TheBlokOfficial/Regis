"""Wejście/wyjście audio na realnym sprzęcie — mikrofon (`MicCapture`), głośnik
(`SpeakerPlayback`) i lokalna synteza tonów wake/stop (`synth_tone`), przez
`sounddevice` (PortAudio, działa na Windows/Linux) i `numpy`.

Format zawsze zgodny z kontraktem WS (`shared.voice_protocol`): PCM16 mono,
16 kHz. Ramki mikrofonu mają stały rozmiar (`FRAME_DURATION_MS`), spójny z
ramkami, jakie `SilenceVadDetector`/serwerowy `ThresholdEnergyWakeWordDetector`
oczekują do analizy.
"""

from __future__ import annotations

import asyncio

import numpy as np
import sounddevice as sd

from shared import CHANNELS, SAMPLE_RATE_HZ, get_logger

logger = get_logger("regis.desktop_satellite.audio")

FRAME_DURATION_MS = 20.0
FRAME_SAMPLES = round(SAMPLE_RATE_HZ * FRAME_DURATION_MS / 1000.0)


class MicCapture:
    """Przechwytuje mikrofon w tle (wątek PortAudio) i udostępnia ramki PCM16 jako
    asynchroniczny strumień — `callback` sounddevice biegnie poza pętlą asyncio,
    więc przekazanie do kolejki musi iść przez `call_soon_threadsafe`."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bytes] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stream: sd.RawInputStream | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE_HZ,
            channels=CHANNELS,
            dtype="int16",
            blocksize=FRAME_SAMPLES,
            callback=self._on_audio,
        )
        self._stream.start()
        logger.info("Mikrofon uruchomiony.")

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("Mikrofon zatrzymany.")

    def _on_audio(self, indata: bytes, frames: int, time_info: object, status: sd.CallbackFlags) -> None:
        del frames, time_info
        if status:
            logger.warning(f"Status strumienia mikrofonu: {status}")
        assert self._loop is not None and self._queue is not None
        chunk = bytes(indata)
        self._loop.call_soon_threadsafe(self._queue.put_nowait, chunk)

    async def frames(self) -> bytes:
        """Zwraca kolejną ramkę PCM16 — czeka, aż `callback` coś dostarczy."""
        assert self._queue is not None, "MicCapture.start() nie zostało wywołane."
        return await self._queue.get()


class SpeakerPlayback:
    """Odtwarza bufor PCM16 przez głośnik — blokujące wywołanie PortAudio wykonywane
    w wątku wykonawczym, żeby nie blokować pętli asyncio."""

    async def play(self, pcm_audio: bytes) -> None:
        if not pcm_audio:
            return
        samples = np.frombuffer(pcm_audio, dtype=np.int16)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._play_blocking, samples)

    @staticmethod
    def _play_blocking(samples: np.ndarray) -> None:
        sd.play(samples, samplerate=SAMPLE_RATE_HZ, blocking=True)


def synth_tone(freq_hz: float, duration_ms: float, amplitude: float = 0.3) -> bytes:
    """Generuje krótki sinusoidalny beep (PCM16 mono) — lokalny dźwięk wake/stop-tone,
    zero zależności od plików audio, zero strumieniowania z serwera (zgodne z
    `shared.voice_protocol`: dźwięki wake/stop-tone są zawsze lokalne)."""
    sample_count = round(SAMPLE_RATE_HZ * duration_ms / 1000.0)
    t = np.linspace(0, duration_ms / 1000.0, sample_count, endpoint=False)
    tone = np.sin(2 * np.pi * freq_hz * t)
    # Krótka obwiednia fade-in/fade-out, żeby uniknąć trzasków na krawędziach.
    fade_samples = max(1, sample_count // 10)
    envelope = np.ones(sample_count)
    envelope[:fade_samples] = np.linspace(0, 1, fade_samples)
    envelope[-fade_samples:] = np.linspace(1, 0, fade_samples)
    pcm = (tone * envelope * amplitude * np.iinfo(np.int16).max).astype(np.int16)
    return pcm.tobytes()
