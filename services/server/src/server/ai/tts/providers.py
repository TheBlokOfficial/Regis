"""Konkretni dostawcy TTS. Protokół (`BaseTTSProvider`) zostaje w `server.voice.tts`.

`ElevenLabsTTSProvider` woła ElevenLabs (`AsyncElevenLabs`) — kontrakt
zweryfikowany bezpośrednio (dokumentacja + inspekcja zainstalowanego SDK, nie
zgadywany). `MockTTSProvider` pozostaje dev-providerem (fallback gdy
`VoiceProvidersConfig.elevenlabs_api_key` puste, patrz `ai/tts/factory.py`).
"""

from __future__ import annotations

from typing import AsyncIterator

from shared import SAMPLE_RATE_HZ, SAMPLE_WIDTH_BYTES

from server.voice.tts import BaseTTSProvider

_MIN_DURATION_SECONDS = 0.2
_MAX_DURATION_SECONDS = 10.0
_CHARS_PER_SECOND = 15.0
# Rozmiar pojedynczego fragmentu ciszy — 200ms, ten sam rząd wielkości co realne ramki
# ElevenLabs. Chodzi o to, żeby testy strumieniowania (i ręczne demo bez klucza API)
# widziały REALNIE wiele fragmentów, nie jeden wielki blok udający strumień.
_MOCK_CHUNK_DURATION_SECONDS = 0.2


class MockTTSProvider(BaseTTSProvider):
    """Deterministyczny dev-provider — strumieniuje ciszę o długości ~proporcjonalnej do
    tekstu, w kawałkach po `_MOCK_CHUNK_DURATION_SECONDS`."""

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        duration_seconds = max(_MIN_DURATION_SECONDS, min(len(text) / _CHARS_PER_SECOND, _MAX_DURATION_SECONDS))
        total_samples = int(SAMPLE_RATE_HZ * duration_seconds)
        chunk_samples = max(1, int(SAMPLE_RATE_HZ * _MOCK_CHUNK_DURATION_SECONDS))
        remaining = total_samples
        while remaining > 0:
            this_chunk = min(chunk_samples, remaining)
            yield b"\x00" * (this_chunk * SAMPLE_WIDTH_BYTES)
            remaining -= this_chunk


class ElevenLabsTTSProvider(BaseTTSProvider):
    """TTS przez ElevenLabs — `AsyncElevenLabs.text_to_speech.convert()` z
    `output_format="pcm_16000"`: dokładnie nasz format przewodowy (PCM16 mono
    16kHz, `shared.voice_protocol`), zero resamplingu. `convert()` już zwraca
    `AsyncIterator[bytes]` — przekazujemy te fragmenty dalej wprost, zamiast (jak
    poprzednio) czekać, aż dopłyną wszystkie, i dopiero wtedy sklejać jeden bufor."""

    def __init__(self, api_key: str, voice_id: str, model_id: str) -> None:
        from elevenlabs.client import AsyncElevenLabs

        self._client = AsyncElevenLabs(api_key=api_key)
        self._voice_id = voice_id
        self._model_id = model_id

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        chunks = self._client.text_to_speech.convert(
            voice_id=self._voice_id,
            text=text,
            model_id=self._model_id,
            output_format="pcm_16000",
        )
        async for chunk in chunks:
            yield chunk
