"""Konkretni dostawcy STT. Protokół (`BaseSTTProvider`) zostaje w `server.voice.stt`.

`GroqSTTProvider` woła Groq (Whisper przez ich API, `AsyncGroq`) — kontrakt
zweryfikowany bezpośrednio (dokumentacja + inspekcja zainstalowanego SDK, nie
zgadywany). `MockSTTProvider` pozostaje dev-providerem (fallback gdy
`VoiceProvidersConfig.groq_api_key` puste, patrz `ai/stt/factory.py`).
"""

from __future__ import annotations

import io
import wave

from shared import CHANNELS, SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES

from server.voice.stt import BaseSTTProvider


class MockSTTProvider(BaseSTTProvider):
    """Deterministyczny dev-provider — nie woła żadnej chmury, zwraca stały tekst."""

    def __init__(self, fixed_transcript: str = "Testowa wiadomość głosowa.") -> None:
        self._fixed_transcript = fixed_transcript

    async def transcribe(self, pcm_audio: bytes) -> str:
        del pcm_audio
        return self._fixed_transcript


class GroqSTTProvider(BaseSTTProvider):
    """STT przez Groq — `AsyncGroq.audio.transcriptions.create()`. Groq (jak
    większość API transkrypcji) przyjmuje pliki audio, nie goły strumień PCM —
    surowe PCM16 owijane jest w minimalny nagłówek WAV (`_pcm_to_wav`) przed
    wysyłką. Język zahardkodowany na `"pl"` — jedyny język, jakim posługuje się
    ten asystent (patrz `WorldPromptStore`/persona)."""

    def __init__(self, api_key: str, model: str) -> None:
        from groq import AsyncGroq

        self._client = AsyncGroq(api_key=api_key)
        self._model = model

    async def transcribe(self, pcm_audio: bytes) -> str:
        wav_bytes = _pcm_to_wav(pcm_audio)
        transcription = await self._client.audio.transcriptions.create(
            model=self._model,
            file=("audio.wav", wav_bytes, "audio/wav"),
            language="pl",
        )
        return transcription.text


def _pcm_to_wav(pcm_audio: bytes) -> bytes:
    """Owija surowe PCM16 mono w minimalny nagłówek WAV — czysta funkcja,
    testowalna bez sieci."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(CHANNELS)
        wav_file.setsampwidth(SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(SAMPLE_RATE_HZ)
        wav_file.writeframes(pcm_audio)
    return buffer.getvalue()
