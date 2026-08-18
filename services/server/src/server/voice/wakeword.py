"""Detektor wake-word — jeden, świeży detektor per połączenie (własny bufor/stan).

Docelowo: streaming inference nad modelem `.onnx` dostarczonym przez użytkownika
(ścieżka/format pliku modelu nie są jeszcze ustalone — poza zakresem tej
implementacji, patrz plan). `ThresholdEnergyWakeWordDetector` to świadomy
placeholder dev/testowy — NIE rozpoznaje słów, tylko sekwencję głośnych ramek —
wystarcza do przetestowania całego protokołu WS end-to-end (symulator satelity,
testy jednostkowe automatu stanu) zanim realny model zostanie podłączony.
"""

from __future__ import annotations

import struct
from typing import Protocol


class WakeWordDetector(Protocol):
    """Kontrakt detektora — implementacje trzymają własny, mutowalny stan/bufor."""

    def process(self, pcm_chunk: bytes) -> bool:
        """Karmi detektor kolejną porcją PCM16 mono; zwraca True dokładnie raz przy wykryciu."""
        ...

    def reset(self) -> None:
        """Czyści wewnętrzny bufor/stan — wywoływane po powrocie do nasłuchu wake-wordu."""
        ...


class ThresholdEnergyWakeWordDetector:
    """Placeholder: wyzwala się po N kolejnych ramkach powyżej progu amplitudy.

    Zastępczy do czasu podłączenia realnego modelu `.onnx`. Nowa instancja
    wymagana per połączenie — stan (`_consecutive_loud_frames`) nie jest
    bezpieczny do współdzielenia między satelitami.
    """

    def __init__(self, loud_frames_required: int = 3, amplitude_threshold: int = 2000) -> None:
        self._loud_frames_required = loud_frames_required
        self._amplitude_threshold = amplitude_threshold
        self._consecutive_loud_frames = 0

    def process(self, pcm_chunk: bytes) -> bool:
        if _peak_amplitude(pcm_chunk) >= self._amplitude_threshold:
            self._consecutive_loud_frames += 1
        else:
            self._consecutive_loud_frames = 0

        if self._consecutive_loud_frames >= self._loud_frames_required:
            self._consecutive_loud_frames = 0
            return True
        return False

    def reset(self) -> None:
        self._consecutive_loud_frames = 0


def _peak_amplitude(pcm_chunk: bytes) -> int:
    """Szczytowa amplituda próbek PCM16 mono w danej porcji (0 dla pustej/nieparzystej porcji)."""
    sample_count = len(pcm_chunk) // 2
    if sample_count == 0:
        return 0
    samples = struct.unpack(f"<{sample_count}h", pcm_chunk[: sample_count * 2])
    return max(abs(s) for s in samples)
