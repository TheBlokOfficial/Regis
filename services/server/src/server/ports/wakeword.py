"""Port detektora wake-word. Konkrety (`OnnxWakeWordDetector`,
`ThresholdEnergyWakeWordDetector`) mieszkają w `server.ai.wakeword` — razem
z pozostałymi adapterami AI, bo model `.onnx` jest takim samym konkretem
dostawcy jak Groq czy ElevenLabs, tylko uruchamianym lokalnie.
"""

from __future__ import annotations

from typing import Protocol


class WakeWordDetector(Protocol):
    """Kontrakt detektora — implementacje trzymają własny, mutowalny stan/bufor,
    więc każde połączenie satelity dostaje świeżą instancję (patrz `main.py`,
    `_build_wakeword_detector_factory`)."""

    def process(self, pcm_chunk: bytes) -> bool:
        """Karmi detektor kolejną porcją PCM16 mono; zwraca True dokładnie raz przy wykryciu."""
        ...

    def reset(self) -> None:
        """Czyści wewnętrzny bufor/stan — wywoływane po powrocie do nasłuchu wake-wordu."""
        ...

    @property
    def last_score(self) -> float | None:
        """Wynik (0-1) ostatniego inference, `None` gdy detektor nie ma pojęcia ciągłego
        score (np. `ThresholdEnergyWakeWordDetector`). Czytane przez `VoiceSession` przy
        wykryciu, do rozgłoszenia pewności detekcji (`VoiceEventType.SATELLITE_WAKE_WORD_DETECTED`,
        Web UI zakładka Klienci) — samo `process()` zwraca tylko bool."""
        ...
