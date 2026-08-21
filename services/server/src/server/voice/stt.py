"""STT — transkrypcja audio -> tekst. `BaseSTTProvider` to mirror `BaseLLMProvider`
(`agent/llm.py`). Konkretni dostawcy (`GroqSTTProvider`, `MockSTTProvider`) oraz
logika wyboru (`STTRegistry`/`STTFactory`) mieszkają w `server.ai.stt` — ten moduł
trzyma wyłącznie protokół, dokładnie jak Kernel trzyma `BaseLLMProvider`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSTTProvider(ABC):
    """Abstrakcyjna klasa bazowa dla dostawców STT."""

    @abstractmethod
    async def transcribe(self, pcm_audio: bytes) -> str:
        """Transkrybuje surowe PCM16 mono (parametry próbkowania: `voice/protocol.py`)."""
        ...

    async def get_active_provider_class_name(self) -> str:
        """Nazwa klasy faktycznie realizującej zadanie. Domyślnie własna klasa —
        `STTRouter` (`server.ai.stt`) nadpisuje, by zwrócić nazwę rozwiązanego konkretu."""
        return type(self).__name__
