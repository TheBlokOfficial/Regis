import numpy as np

class EnergyVAD:
    """Własny VAD bazujący na energii RMS z wygładzaniem (hangover) zapobiegającym szatkowaniu."""
    def __init__(self, threshold=300, hangover_frames=4):
        self.threshold = threshold
        self.hangover_frames = hangover_frames  # 4 * 100ms = 400ms podtrzymania stanu mowy
        self._counter = 0
        
    def is_speech(self, chunk: np.ndarray) -> bool:
        # np.ndarray to macierz w int16
        # Liczymy głośność z użyciem float32 by zapobiec overflow
        rms = np.sqrt(np.mean(chunk.astype(np.float32)**2))
        if rms >= self.threshold:
            self._counter = self.hangover_frames
            return True
        else:
            if self._counter > 0:
                self._counter -= 1
                return True
            return False
