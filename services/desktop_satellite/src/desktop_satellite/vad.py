"""Lokalny detektor końca wypowiedzi (VAD) — działa po stronie satelity, zgodnie z
protokołem (`utterance_end` to wiadomość *od* satelity, patrz `shared.voice_protocol`)
i świadomą decyzją architektoniczną (`docs/manifest.md`, sekcja 5, "VAD po stronie
satelity, nie serwera"): to satelita i tak musi wiedzieć lokalnie, kiedy przestać
nagrywać/strumieniować, więc scentralizowanie tej decyzji po stronie serwera nie
eliminowałoby potrzeby logiki lokalnej, tylko dodawało drugą bez korzyści.

Czysta klasa (mirror stylu `ThresholdEnergyWakeWordDetector` z
`server/voice/wakeword.py`) — zero zależności od audio I/O, testowalna w izolacji.
"""

from __future__ import annotations

import struct

from shared import SAMPLE_RATE_HZ


class SilenceVadDetector:
    """Wyzwala się po `silence_duration_ms` ciągłej ciszy (amplituda poniżej progu)
    następującej po co najmniej jednej głośnej ramce — czyli po realnej wypowiedzi,
    nie od razu na starcie nagrywania."""

    def __init__(
        self,
        frame_duration_ms: float,
        silence_duration_ms: float = 1500.0,
        amplitude_threshold: int = 500,
    ) -> None:
        self._frames_required = max(1, round(silence_duration_ms / frame_duration_ms))
        self._amplitude_threshold = amplitude_threshold
        self._consecutive_silent_frames = 0
        self._heard_speech = False

    def process(self, pcm_chunk: bytes) -> bool:
        if _peak_amplitude(pcm_chunk) >= self._amplitude_threshold:
            self._heard_speech = True
            self._consecutive_silent_frames = 0
            return False

        if not self._heard_speech:
            return False

        self._consecutive_silent_frames += 1
        return self._consecutive_silent_frames >= self._frames_required

    def reset(self) -> None:
        self._consecutive_silent_frames = 0
        self._heard_speech = False


def _peak_amplitude(pcm_chunk: bytes) -> int:
    """Szczytowa amplituda próbek PCM16 mono w danej porcji (0 dla pustej/nieparzystej porcji)."""
    sample_count = len(pcm_chunk) // 2
    if sample_count == 0:
        return 0
    samples = struct.unpack(f"<{sample_count}h", pcm_chunk[: sample_count * 2])
    return max(abs(s) for s in samples)


def frame_duration_ms(frame_sample_count: int, sample_rate_hz: int = SAMPLE_RATE_HZ) -> float:
    """Czas trwania jednej ramki PCM (w ms) dla danej liczby próbek — pomocnicze przy
    konfigurowaniu `SilenceVadDetector` zgodnie z rozmiarem ramek używanych przez `MicCapture`."""
    return (frame_sample_count / sample_rate_hz) * 1000.0
