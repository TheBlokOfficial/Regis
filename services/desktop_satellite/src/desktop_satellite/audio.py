"""Wejście/wyjście audio na realnym sprzęcie — mikrofon (`MicCapture`), głośnik
(`SpeakerPlayback`) przez `sounddevice` (PortAudio, działa na Windows/Linux) i
`numpy`. Dźwięki wake/stop-tone (`SpeakerPlayback.play_cue`) preferują wbudowane
dźwięki systemowe Windows (`C:\\Windows\\Media\\*.wav` — własność użytkownika,
część każdej instalacji Windows, nigdy nie kopiowane do repo), z fallbackiem do
lokalnie syntezowanego tonu (`synth_tone`) na Linux albo gdy plik nie istnieje.

Format zawsze zgodny z kontraktem WS (`shared.voice_protocol`): PCM16 mono,
16 kHz. Ramki mikrofonu mają stały rozmiar (`FRAME_DURATION_MS`), spójny z
ramkami, jakie `SilenceVadDetector`/serwerowy `ThresholdEnergyWakeWordDetector`
oczekują do analizy.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np
import sounddevice as sd

from shared import CHANNELS, SAMPLE_RATE_HZ, get_logger

logger = get_logger("regis.desktop_satellite.audio")

FRAME_DURATION_MS = 20.0
FRAME_SAMPLES = round(SAMPLE_RATE_HZ * FRAME_DURATION_MS / 1000.0)

WINDOWS_MEDIA_DIR = Path(r"C:\Windows\Media")


def _windows_system_sound_path(sound_name: str) -> Path | None:
    """Ścieżka do wbudowanego dźwięku systemowego Windows (Speech Recognition —
    `Speech On`/`Speech Sleep` itd., `C:\\Windows\\Media\\*.wav`) — te same dźwięki,
    które kiedyś towarzyszyły Cortanie. Pliki są częścią każdej instalacji Windows
    (własność użytkownika), nigdy nie kopiowane do repo — `None` na Linux/gdy plik
    nie istnieje (np. edycja Windows bez funkcji multimedialnych)."""
    if sys.platform != "win32":
        return None
    path = WINDOWS_MEDIA_DIR / f"{sound_name}.wav"
    return path if path.exists() else None


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
    """Odtwarza audio przez głośnik — blokujące wywołania PortAudio wykonywane w wątku
    wykonawczym, żeby nie blokować pętli asyncio.

    `start_stream()`/`write_chunk()`/`stop_stream()` to ścieżka STRUMIENIOWA (patrz
    `SatelliteSession`, protokół `tts_start` -> N ramek binarnych -> `tts_end`): kolejne
    fragmenty audio od serwera grają w miarę nadejścia, przez otwarty `RawOutputStream`,
    zamiast czekać na dogranie się wszystkich ramek do bufora i dopiero wtedy odtwarzać
    `play()` na komplecie (jak działało to wcześniej) — przy dłuższej odpowiedzi to
    różnica między dźwiękiem od razu a ciszą przez kilka sekund. `play()` zostaje jako
    prostsza ścieżka NIEstrumieniowa, używana wyłącznie do lokalnych dźwięków
    wake/stop-tone (`play_cue`), gdzie cały bufor i tak powstaje lokalnie w jednej
    chwili — otwieranie dla nich osobnego strumienia byłoby zbędnym narzutem."""

    def __init__(self) -> None:
        self._stream: sd.RawOutputStream | None = None

    async def play(self, pcm_audio: bytes) -> None:
        if not pcm_audio:
            return
        samples = np.frombuffer(pcm_audio, dtype=np.int16)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._play_blocking, samples)

    async def start_stream(self) -> None:
        """Otwiera wyjściowy strumień audio — wołane raz po odebraniu `tts_start`,
        zanim przyjdzie pierwsza ramka binarna.

        Defensywnie zamyka POPRZEDNI strumień, jeśli jakiś został otwarty, a nigdy nie
        doczekał się `stop_stream()` (np. WS padł w połowie odtwarzania, satelita
        wznowiła połączenie i serwer zaczął nową turę) — bez tego uchwyt PortAudio
        poprzedniego strumienia by przeciekł, nadpisany bez zamknięcia."""
        if self._stream is not None:
            await self._abort_leftover_stream()
        loop = asyncio.get_running_loop()
        stream = sd.RawOutputStream(samplerate=SAMPLE_RATE_HZ, channels=CHANNELS, dtype="int16")
        await loop.run_in_executor(None, stream.start)
        self._stream = stream

    async def _abort_leftover_stream(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is None:
            return
        loop = asyncio.get_running_loop()
        # `abort()`, nie `stop()`: ten strumień jest osierocony (nikt już nie czeka na
        # dogranie jego bufora), więc czekanie na jego naturalny koniec tylko opóźniałoby
        # start nowej odpowiedzi bez żadnej korzyści.
        await loop.run_in_executor(None, stream.abort)
        await loop.run_in_executor(None, stream.close)

    async def write_chunk(self, pcm_audio: bytes) -> None:
        """Dokłada fragment do strumienia — blokuje tylko do momentu, aż PortAudio
        przyjmie dane do WEWNĘTRZNEGO bufora (nie do końca ich odegrania), więc nie
        wstrzymuje odbioru kolejnych ramek WS na dłużej niż to konieczne."""
        if not pcm_audio or self._stream is None:
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._stream.write, pcm_audio)

    async def stop_stream(self) -> None:
        """Zamyka strumień — `stream.stop()` **czeka, aż wszystkie już przyjęte ramki
        dograją się do końca**, więc `playback_done` (wysyłane zaraz po tym wywołaniu
        przez `SatelliteSession`) naprawdę oznacza koniec odtwarzania, nie tylko koniec
        odbierania danych. Gdyby użyć `abort()` zamiast `stop()`, ostatni fragment
        odpowiedzi ucinałby się w połowie dźwięku."""
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, stream.stop)
        await loop.run_in_executor(None, stream.close)

    async def play_cue(self, windows_sound_name: str, fallback_pcm: bytes) -> None:
        """Odtwarza dźwięk systemowy Windows (`windows_sound_name`, patrz
        `_windows_system_sound_path`); gdy niedostępny (Linux, brak pliku) — odtwarza
        `fallback_pcm` (lokalnie syntezowany ton, patrz `synth_tone`)."""
        path = _windows_system_sound_path(windows_sound_name)
        if path is None:
            await self.play(fallback_pcm)
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._play_system_sound_blocking, path)

    @staticmethod
    def _play_blocking(samples: np.ndarray) -> None:
        sd.play(samples, samplerate=SAMPLE_RATE_HZ, blocking=True)

    @staticmethod
    def _play_system_sound_blocking(path: Path) -> None:
        import winsound

        winsound.PlaySound(str(path), winsound.SND_FILENAME)


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
