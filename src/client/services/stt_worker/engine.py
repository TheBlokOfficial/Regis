import logging
import os
import sys

# Windows DLL loading fix for nvidia pip packages
if os.name == 'nt':
    try:
        import site
        site_packages = site.getsitepackages()
        for sp in site_packages:
            cublas_path = os.path.join(sp, "nvidia", "cublas", "bin")
            cudnn_path = os.path.join(sp, "nvidia", "cudnn", "bin")
            if os.path.exists(cublas_path):
                os.add_dll_directory(cublas_path)
                os.environ["PATH"] += os.pathsep + cublas_path
            if os.path.exists(cudnn_path):
                os.add_dll_directory(cudnn_path)
                os.environ["PATH"] += os.pathsep + cudnn_path
    except Exception as e:
        logging.warning(f"Nie udało się załadować ścieżek DLL dla CUDA: {e}")

from faster_whisper import WhisperModel


class STTEngine:
    def __init__(self, model_size="small", language="pl"):
        logging.info(f"Ładowanie modelu STT faster-whisper (rozmiar: {model_size})...")
        self.language = language
        self.model_size = model_size
        try:
            self.model = WhisperModel(model_size, device="cuda", compute_type="float16")
            logging.info(f"Załadowano faster-whisper na GPU (CUDA, float16).")
        except Exception as e:
            logging.warning(f"Brak GPU lub błąd CUDA, fallback na CPU: {e}")
            self.model = WhisperModel(model_size, device="cpu", compute_type="int8")

    def transcribe_audio_file(self, file_like_object) -> str:
        import wave
        import numpy as np
        logging.info("Rozpoczęto transkrypcję z pliku (faster-whisper)...")

        # Obejście błędów dekodowania ffmpeg/av - ręczne załadowanie do tablicy numpy float32
        with wave.open(file_like_object, 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        kwargs = {
            "language": self.language,
            "beam_size": 5,
            "vad_filter": True,
            "condition_on_previous_text": False,
            "initial_prompt": "Regis, zgaś, zapal, zaświeć, włącz, wyłącz, światło, pracownia, salon, kuchnia, pokój."
        }

        try:
            segments, info = self.model.transcribe(audio_data, **kwargs)
            results = []
            for segment in segments:
                results.append(segment.text)
        except Exception as e:
            logging.warning(f"Błąd inferencji GPU ({e}). Awaryjny fallback STT na CPU...")
            self.model = WhisperModel(self.model_size, device="cpu", compute_type="int8")
            segments, info = self.model.transcribe(audio_data, **kwargs)
            results = []
            for segment in segments:
                results.append(segment.text)

        return " ".join(results).strip()
