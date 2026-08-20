"""Testy czystych funkcji STT/TTS — bez sieci (brak kluczy API w środowisku testowym,
ten sam wybór co dla `MicCapture`/`SpeakerPlayback` w `desktop_satellite`)."""

from __future__ import annotations

import io
import wave

from shared import CHANNELS, SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES

from server.voice.stt import _pcm_to_wav


def test_pcm_to_wav_round_trip() -> None:
    pcm = (1000).to_bytes(2, byteorder="little", signed=True) * 100
    wav_bytes = _pcm_to_wav(pcm)

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnchannels() == CHANNELS
        assert wav_file.getsampwidth() == SAMPLE_WIDTH_BYTES
        assert wav_file.getframerate() == SAMPLE_RATE_HZ
        assert wav_file.readframes(wav_file.getnframes()) == pcm


def test_pcm_to_wav_handles_empty_input() -> None:
    wav_bytes = _pcm_to_wav(b"")
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
        assert wav_file.getnframes() == 0
