"""Adaptery detekcji wake-word. Kontrakt: `server.ports.wakeword.WakeWordDetector`."""

from server.ai.wakeword.detectors import OnnxWakeWordDetector, ThresholdEnergyWakeWordDetector

__all__ = ["OnnxWakeWordDetector", "ThresholdEnergyWakeWordDetector"]
