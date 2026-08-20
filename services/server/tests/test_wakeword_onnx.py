"""Testy `OnnxWakeWordDetector` — smoke test integracji z realnym modelem
`regis.onnx` (`services/server/data/wakeword/`). Bez asercji o rzeczywistej
skuteczności rozpoznawania (to rola `livekit-wakeword eval`, poza tym
repozytorium) — tylko poprawność ładowania modelu, buforowania i resetu.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from server.voice.wakeword import OnnxWakeWordDetector

MODEL_PATH = Path(__file__).parent.parent / "data" / "wakeword" / "regis.onnx"


def _silent_frame(sample_count: int = 320) -> bytes:
    return np.zeros(sample_count, dtype=np.int16).tobytes()


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="Model regis.onnx nie jest obecny w tym środowisku.")
def test_onnx_detector_loads_and_processes_silence_without_crashing() -> None:
    detector = OnnxWakeWordDetector(MODEL_PATH, threshold=0.39)
    for _ in range(50):  # ~1s przy ramkach 20ms — wystarczy na kilka inference (stride 320ms)
        result = detector.process(_silent_frame())
        assert isinstance(result, bool)


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="Model regis.onnx nie jest obecny w tym środowisku.")
def test_onnx_detector_silence_does_not_trigger() -> None:
    detector = OnnxWakeWordDetector(MODEL_PATH, threshold=0.39)
    triggered = any(detector.process(_silent_frame()) for _ in range(120))
    assert triggered is False


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="Model regis.onnx nie jest obecny w tym środowisku.")
def test_reset_clears_buffer_and_stride_counter() -> None:
    detector = OnnxWakeWordDetector(MODEL_PATH, threshold=0.39)
    for _ in range(10):
        detector.process(_silent_frame())
    detector.reset()
    assert len(detector._buffer) == 0
    assert detector._samples_since_predict == 0
