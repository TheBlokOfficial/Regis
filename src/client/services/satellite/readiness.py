import asyncio
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .audio.wakeword import WakeWordEngine
    from .audio.recorder import AudioStreamManager
    from .event_bus import EventBus

class ReadinessChecker:
    """Samoleczący komponent oczekujący na sprawność sprzętu i silników AI."""

    def __init__(self, wakeword: "WakeWordEngine", audio_manager: "AudioStreamManager", event_bus: "EventBus"):
        self.wakeword = wakeword
        self.audio_manager = audio_manager
        self.event_bus = event_bus

    async def ensure_ready(self):
        """Samolecząca pętla – oczekuje w tle na poprawny silnik AI i kartę dźwiękową."""
        last_reason: Optional[str] = None
        while True:
            reason_ww = self._try_init_wakeword(last_reason)
            if reason_ww:
                last_reason = reason_ww
                await asyncio.sleep(5)
                continue
                
            reason_mic = self._try_init_microphone(last_reason)
            if reason_mic:
                last_reason = reason_mic
                await asyncio.sleep(5)
                continue

            self.event_bus.emit({"type": "readiness", "ready": True})
            self.event_bus.emit({"type": "waiting"})
            self.event_bus.log("Sprzęt audio i silniki AI gotowe. Oczekiwanie na sygnał z Kontrolera (WAITING)...")
            break

    def _try_init_wakeword(self, last_reason: Optional[str]) -> Optional[str]:
        if not self.wakeword.is_ready():
            if not self.wakeword.try_init():
                reason = "Brak pliku modelu models/wakeword.onnx"
                if reason != last_reason:
                    self.event_bus.emit({"type": "readiness", "ready": False, "reason": reason})
                    self.event_bus.log(f"Ostrzeżenie: {reason}. Ponawiam za 5s...")
                return reason
        return None

    def _try_init_microphone(self, last_reason: Optional[str]) -> Optional[str]:
        if not self.audio_manager.is_ready():
            try:
                self.audio_manager.start_stream()
            except Exception as e:
                reason = f"Brak lub błąd urządzenia nagrywającego (mikrofonu): {e}"
                if reason != last_reason:
                    self.event_bus.emit({"type": "readiness", "ready": False, "reason": reason})
                    self.event_bus.log(f"Ostrzeżenie: {reason}. Ponawiam za 5s...")
                return reason
        return None
