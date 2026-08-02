import os
import sys
import base64
import wave
import io
import sounddevice as sd
import numpy as np

class AudioPlayer:
    """Odpowiada za odtwarzanie sygnałów dźwiękowych oraz mowy (TTS)."""
    
    @staticmethod
    def play_system_sound(sound_name: str):
        """Odtwarza dźwięki systemowe Windows (np. 'Speech On', 'Speech Sleep')."""
        if sys.platform == 'win32':
            import winsound
            snd_path = rf"C:\Windows\Media\{sound_name}.wav"
            if os.path.exists(snd_path):
                winsound.PlaySound(snd_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

    @staticmethod
    def play_tts_audio(b64_content: str):
        """Dekoduje bazę 64 i odtwarza strumień audio."""
        try:
            audio_data = base64.b64decode(b64_content)
            with wave.open(io.BytesIO(audio_data), 'rb') as wf:
                samplerate = wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                audio_array = np.frombuffer(frames, dtype=np.int16)
                sd.play(audio_array, samplerate)
                sd.wait()
        except Exception as e:
            raise RuntimeError(f"Błąd odtwarzania TTS: {e}")
