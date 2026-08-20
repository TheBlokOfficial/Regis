"""TTS — synteza tekst -> audio. `BaseTTSProvider` to mirror `BaseLLMProvider`
(`agent/backend/providers/base.py`) — konkretny dostawca chmurowy nie jest jeszcze
wybrany (patrz plan implementacji); `MockTTSProvider` generuje ciszę PCM16 o
długości proporcjonalnej do tekstu, wystarczającą do testów pipeline'u bez
kluczy API.
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
