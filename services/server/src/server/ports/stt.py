"""Port STT — transkrypcja audio -> tekst. Mirror `ports/llm.py`.

Konkretni dostawcy (`GroqSTTProvider`, `MockSTTProvider`) i logika wyboru
(`STTRegistry`/`STTFactory`) mieszkają w `server.ai.stt`; konsumentem jest
`server.voice`. Protokół stoi między nimi, w `ports/`, żeby żadna ze stron
nie musiała importować drugiej (patrz `ports/__init__.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseSTTProvider(ABC):
    """Abstrakcyjna klasa bazowa dla dostawców STT."""

    is_placeholder: bool = False
    """Czy to dostawca dev/testowy, a nie realna transkrypcja.

    Deklarowane przez sam konkret, bo tylko on to wie. Wcześniej `GET /voice/status`
    zgadywał po prefiksie nazwy klasy (`name.startswith("Mock")`) — działało dopóty,
    dopóki nikt nie nazwał dostawcy inaczej, a milcząco przestałoby przy pierwszym
    `StubSTTProvider`. Patrz `voice/routes.py`, `is_production_ready`."""

    @abstractmethod
    async def transcribe(self, pcm_audio: bytes) -> str:
        """Transkrybuje surowe PCM16 mono (parametry próbkowania: `shared/voice_protocol.py`)."""
        ...

    async def get_active_provider_class_name(self) -> str:
        """Nazwa klasy faktycznie realizującej zadanie. Domyślnie własna klasa —
        `STTRouter` (`server.ai.stt`) nadpisuje, by zwrócić nazwę rozwiązanego konkretu."""
        return type(self).__name__

    async def is_active_provider_placeholder(self) -> bool:
        """Czy dostawca faktycznie realizujący zadanie jest placeholderem.
        Mirror `get_active_provider_class_name()` — router nadpisuje, by odpytać konkret."""
        return self.is_placeholder
