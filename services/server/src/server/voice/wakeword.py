"""Detektor wake-word — jeden, świeży detektor per połączenie (własny bufor/stan).

`OnnxWakeWordDetector` to realny detektor oparty o wytrenowany model `.onnx`
(biblioteka `livekit-wakeword` — ekstrakcja cech mel-spektrogram+embedding jest
wbudowana w pakiet, tu tylko sklejamy kroczący bufor audio i próg pewności).
`ThresholdEnergyWakeWordDetector` to świadomy placeholder dev/testowy — NIE
rozpoznaje słów, tylko sekwencję głośnych ramek — używany dziś jako fallback,
gdy w `Settings.wakeword_model_path` nie skonfigurowano żadnego modelu (patrz
`main.py`), oraz w testach jednostkowych automatu stanu (`test_voice_pipeline.py`).
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Protocol

import numpy as np
from livekit.wakeword import WakeWordModel

from shared import SAMPLE_RATE_HZ, get_logger

logger = get_logger("regis.voice.wakeword")


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


class OnnxWakeWordDetector:
    """Realny detektor — kroczący bufor ~2s audio, inference co ~320ms (stride),
    zgodnie z zaleceniem `livekit-wakeword` (2s = dokładnie 16 embeddingów, wejście
    klasyfikatora). Krótsze bufory `WakeWordModel.predict()` sam bezpiecznie
    zwraca wynik 0.0 — nie trzeba tego pilnować ręcznie.

    Koszt inference zmierzony empirycznie: ~20ms na wywołanie `predict()` na CPU
    (model `regis.onnx`, ~930KB) — przy stride 320ms to ~6% czasu, akceptowalne
    jako wywołanie synchroniczne (bez `run_in_executor`) przy skali tego projektu
    (jednoosobowy, kilka satelit jednocześnie). Nowa instancja wymagana per
    połączenie — stan bufora nie jest bezpieczny do współdzielenia.
    """

    _WINDOW_SECONDS = 2.0
    _STRIDE_SECONDS = 0.32

    def __init__(self, model_path: str | Path, threshold: float, sample_rate_hz: int = SAMPLE_RATE_HZ) -> None:
        self._model_name = Path(model_path).stem
        self._model = WakeWordModel(models=[model_path])
        self._threshold = threshold
        self._window_samples = round(self._WINDOW_SECONDS * sample_rate_hz)
        self._stride_samples = round(self._STRIDE_SECONDS * sample_rate_hz)
        self._buffer = np.zeros(0, dtype=np.int16)
        self._samples_since_predict = 0
        logger.info(f"Załadowano model wake-word '{self._model_name}' [próg: {threshold}].")

    def process(self, pcm_chunk: bytes) -> bool:
        samples = np.frombuffer(pcm_chunk, dtype=np.int16)
        self._buffer = np.concatenate([self._buffer, samples])[-self._window_samples :]
        self._samples_since_predict += len(samples)

        if self._samples_since_predict < self._stride_samples:
            return False
        self._samples_since_predict = 0

        scores = self._model.predict(self._buffer)
        score = scores.get(self._model_name, 0.0)
        detected = score >= self._threshold
        # DEBUG (nie INFO) — inference co ~320ms podczas całego nasłuchu zalałoby konsolę
        # przy normalnym poziomie logowania. Włącz przez `Settings.debug=true` w config.json,
        # żeby na żywo widzieć bliskie niedomiary (false negative) i co realnie przebiło próg
        # (false positive) — dotąd `score` było liczone i odrzucane bez śladu w logach.
        logger.debug(f"Wake-word score: {score:.3f} [próg: {self._threshold}]{' -> WYKRYTO' if detected else ''}")
        return detected

    def reset(self) -> None:
        self._buffer = np.zeros(0, dtype=np.int16)
        self._samples_since_predict = 0


def _peak_amplitude(pcm_chunk: bytes) -> int:
    """Szczytowa amplituda próbek PCM16 mono w danej porcji (0 dla pustej/nieparzystej porcji)."""
    sample_count = len(pcm_chunk) // 2
    if sample_count == 0:
        return 0
    samples = struct.unpack(f"<{sample_count}h", pcm_chunk[: sample_count * 2])
    return max(abs(s) for s in samples)
