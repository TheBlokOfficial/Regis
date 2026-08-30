"""Lokalna bramka energii ograniczająca wysyłanie ciszy podczas nasłuchu wake-worda."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from shared import peak_amplitude

DEFAULT_PREROLL_MS = 1680.0
DEFAULT_HANGOVER_MS = 800.0


@dataclass(frozen=True)
class WakeGateEmission:
    """Ramki do wysłania i informacja, czy serwer ma zacząć nowy bufor detekcji."""

    starts_stream: bool
    frames: tuple[bytes, ...]


class WakeAudioGate:
    """Przepuszcza porcję audio od pierwszej głośnej ramki do końca krótkiej ciszy.

    Zamknięta bramka zachowuje pre-roll dłuższy niż różnica między 2-sekundowym
    oknem modelu a jego 320-ms krokiem. Dzięki temu pierwsza pełna predykcja zawiera
    początek słowa, mimo że decyzję o otwarciu podejmujemy dopiero po usłyszeniu głosu.
    """

    def __init__(
        self,
        frame_duration_ms: float,
        amplitude_threshold: int,
        preroll_ms: float = DEFAULT_PREROLL_MS,
        hangover_ms: float = DEFAULT_HANGOVER_MS,
    ) -> None:
        self._amplitude_threshold = amplitude_threshold
        self._preroll_frames = max(1, round(preroll_ms / frame_duration_ms))
        self._hangover_frames = max(1, round(hangover_ms / frame_duration_ms))
        self._buffer: deque[bytes] = deque(maxlen=self._preroll_frames)
        self._open = False
        self._consecutive_silent_frames = 0

    def process(self, pcm_chunk: bytes) -> WakeGateEmission:
        loud = peak_amplitude(pcm_chunk) >= self._amplitude_threshold

        if not self._open:
            self._buffer.append(pcm_chunk)
            if not loud:
                return WakeGateEmission(starts_stream=False, frames=())

            self._open = True
            self._consecutive_silent_frames = 0
            frames = tuple(self._buffer)
            self._buffer.clear()
            return WakeGateEmission(starts_stream=True, frames=frames)

        if loud:
            self._consecutive_silent_frames = 0
        else:
            self._consecutive_silent_frames += 1
            if self._consecutive_silent_frames >= self._hangover_frames:
                self._open = False
                self._consecutive_silent_frames = 0

        return WakeGateEmission(starts_stream=False, frames=(pcm_chunk,))

    def reset(self) -> None:
        self._buffer.clear()
        self._open = False
        self._consecutive_silent_frames = 0
