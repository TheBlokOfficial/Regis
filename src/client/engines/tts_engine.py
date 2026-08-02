import logging
import os
import wave
import io
import base64
import requests

try:
    from piper.voice import PiperVoice
except ImportError:
    PiperVoice = None


class TTSEngine:
    def __init__(self, model_name="pl_PL-darkman-medium"):
        self.model_name = model_name
        self.model_dir = os.path.join("data", "models")
        self.onnx_path = os.path.join(self.model_dir, f"{model_name}.onnx")
        self.json_path = os.path.join(self.model_dir, f"{model_name}.onnx.json")
        self.voice = None
        
        if PiperVoice is None:
            logging.error("Biblioteka 'piper-tts' nie jest zainstalowana. TTS nie zadziała.")
            return

        self._ensure_model_downloaded()
        
        try:
            logging.info(f"Ładowanie modelu TTS: {model_name}...")
            self.voice = PiperVoice.load(self.onnx_path, config_path=self.json_path)
            logging.info(f"Model TTS {model_name} załadowany pomyślnie.")
        except Exception as e:
            logging.error(f"Nie udało się załadować modelu TTS: {e}")

    def _ensure_model_downloaded(self):
        """Pobiera model z Hugging Face, jeśli nie istnieje."""
        os.makedirs(self.model_dir, exist_ok=True)
        # Zakładamy format np. pl_PL-darkman-medium
        voice_name = self.model_name.split('-')[1]
        base_url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/pl/pl_PL/{voice_name}/medium/{self.model_name}"
        
        for path, ext in [(self.onnx_path, ".onnx"), (self.json_path, ".onnx.json")]:
            if not os.path.exists(path):
                url = base_url + ext
                logging.info(f"Pobieranie modelu TTS: {url} do {path}")
                try:
                    response = requests.get(url, stream=True)
                    response.raise_for_status()
                    with open(path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    logging.info(f"Pobrano pomyślnie: {ext}")
                except Exception as e:
                    logging.error(f"Błąd pobierania {ext}: {e}")
                    if os.path.exists(path):
                        os.remove(path)

    def synthesize_to_base64(self, text: str) -> str:
        """
        Generuje audio na podstawie tekstu, zapisuje do bufora jako WAV 
        i koduje do Base64.
        """
        if not self.voice or not text.strip():
            return ""
            
        try:
            wav_io = io.BytesIO()
            with wave.open(wav_io, "wb") as wav_file:
                self.voice.synthesize_wav(text, wav_file)
            
            wav_data = wav_io.getvalue()
            b64_audio = base64.b64encode(wav_data).decode("utf-8")
            return b64_audio
        except Exception as e:
            logging.exception(f"Błąd podczas syntezy TTS: {e}")
            return ""
