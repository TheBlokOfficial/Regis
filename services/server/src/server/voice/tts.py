"""TTS — synteza tekst -> audio. `BaseTTSProvider` to mirror `BaseLLMProvider`
(`agent/llm.py`). Konkretni dostawcy (`ElevenLabsTTSProvider`, `MockTTSProvider`)
oraz logika wyboru (`TTSRegistry`/`TTSFactory`) mieszkają w `server.ai.tts` — ten
moduł trzyma wyłącznie protokół, dokładnie jak Kernel trzyma `BaseLLMProvider`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTTSProvider(ABC):
    """Abstrakcyjna klasa bazowa dla dostawców TTS."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Syntezuje tekst do surowego PCM16 mono (parametry próbkowania: `voice/protocol.py`)."""
        ...

    async def get_active_provider_class_name(self) -> str:
        """Nazwa klasy faktycznie realizującej zadanie. Domyślnie własna klasa —
        `TTSRouter` (`server.ai.tts`) nadpisuje, by zwrócić nazwę rozwiązanego konkretu."""
        return type(self).__name__
