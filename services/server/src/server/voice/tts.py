"""TTS — synteza tekst -> audio. `BaseTTSProvider` to mirror `BaseLLMProvider`
(`agent/backend/providers/base.py`). `ElevenLabsTTSProvider` woła ElevenLabs
(`AsyncElevenLabs`) — kontrakt zweryfikowany bezpośrednio (dokumentacja +
inspekcja zainstalowanego SDK, nie zgadywany). `MockTTSProvider` pozostaje
dev-providerem (fallback gdy `VoiceProvidersConfig.elevenlabs_api_key` puste,
patrz `main.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from shared import SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES

_MIN_DURATION_SECONDS = 0.2
_MAX_DURATION_SECONDS = 10.0
_CHARS_PER_SECOND = 15.0


class BaseTTSProvider(ABC):
    """Abstrakcyjna klasa bazowa dla dostawców TTS."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Syntezuje tekst do surowego PCM16 mono (parametry próbkowania: `voice/protocol.py`)."""
        ...


class MockTTSProvider(BaseTTSProvider):
    """Deterministyczny dev-provider — generuje ciszę o długości ~proporcjonalnej do tekstu."""

    async def synthesize(self, text: str) -> bytes:
        duration_seconds = max(_MIN_DURATION_SECONDS, min(len(text) / _CHARS_PER_SECOND, _MAX_DURATION_SECONDS))
        sample_count = int(SAMPLE_RATE_HZ * duration_seconds)
        return b"\x00" * (sample_count * SAMPLE_WIDTH_BYTES)


class ElevenLabsTTSProvider(BaseTTSProvider):
    """TTS przez ElevenLabs — `AsyncElevenLabs.text_to_speech.convert()` z
    `output_format="pcm_16000"`: dokładnie nasz format przewodowy (PCM16 mono
    16kHz, `shared.voice_protocol`), zero resamplingu. `convert()` zwraca
    `AsyncIterator[bytes]` (strumień) — sklejany do jednego bufora, bo
    `BaseTTSProvider.synthesize()` zwraca kompletne audio, nie strumień."""

    def __init__(self, api_key: str, voice_id: str, model_id: str) -> None:
        from elevenlabs.client import AsyncElevenLabs

        self._client = AsyncElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model_id = model_id

    async def synthesize(self, text: str) -> bytes:
        chunks = self._client.text_to_speech.convert(
            voice_id=self._voice_id,
            text=text,
            model_id=self._model_id,
            output_format="pcm_16000",
        )
        return b"".join([chunk async for chunk in chunks])
