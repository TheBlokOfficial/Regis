"""STT — transkrypcja audio -> tekst. `BaseSTTProvider` to mirror `BaseLLMProvider`
(`agent/backend/providers/base.py`) — konkretny dostawca chmurowy nie jest jeszcze
wybrany (patrz plan implementacji); `MockSTTProvider` pozwala przetestować cały
pipeline WS end-to-end już teraz, bez kluczy API.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSTTProvider(ABC):
    """Abstrakcyjna klasa bazowa dla dostawców STT."""

    @abstractmethod
    async def transcribe(self, pcm_audio: bytes) -> str:
        """Transkrybuje surowe PCM16 mono (parametry próbkowania: `voice/protocol.py`)."""
        ...


class MockSTTProvider(BaseSTTProvider):
    """Deterministyczny dev-provider — nie woła żadnej chmury, zwraca stały tekst."""

    def __init__(self, fixed_transcript: str = "Testowa wiadomość głosowa.") -> None:
        self._fixed_transcript = fixed_transcript

    async def transcribe(self, pcm_audio: bytes) -> str:
        del pcm_audio
        return self._fixed_transcript
