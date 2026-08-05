import os
import logging

try:
    from openwakeword.model import Model
    from openwakeword.utils import download_models
except ImportError:
    Model = None
    download_models = None

class WakeWordEngine:
    """Silnik obsługujący model Wake Word (openwakeword)."""
    
    def __init__(self, data_dir: str):
        self.data_dir = data_dir
        self.model = None
        self.model_path = os.path.abspath(os.path.join(data_dir, "models", "wakeword.onnx"))
        self.try_init()

    def is_ready(self) -> bool:
        return self.model is not None

    def try_init(self) -> bool:
        if self.model is not None:
            return True
            
        if Model is None:
            return False

        if not os.path.exists(self.model_path):
            return False

        try:
            if download_models:
                try:
                    download_models()
                except Exception:
                    pass
            self.model = Model(wakeword_models=[self.model_path], inference_framework="onnx")
            return True
        except Exception as e:
            logging.warning(f"Nie udało się załadować modelu {self.model_path}: {e}")
            self.model = None
            return False

    def predict(self, pcm16_1d) -> dict:
        if not self.model:
            return {}
        return self.model.predict(pcm16_1d)

    def reset(self):
        if self.model:
            self.model.reset()
