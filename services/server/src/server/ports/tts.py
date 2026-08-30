"""Port TTS — synteza tekst -> audio. Mirror `ports/llm.py`.

Konkretni dostawcy (`ElevenLabsTTSProvider`, `MockTTSProvider`) i logika wyboru
(`TTSRegistry`/`TTSFactory`) mieszkają w `server.ai.tts`; konsumentem jest
`server.voice`. Protokół stoi między nimi, w `ports/` (patrz `ports/__init__.py`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseTTSProvider(ABC):
    """Abstrakcyjna klasa bazowa dla dostawców TTS.

    `synthesize_stream` jest prymitywem (mirror `BaseLLMProvider.generate_stream`) —
    yielduje kolejne fragmenty PCM16 mono w miarę ich powstawania, zamiast czekać na
    całość. Bez tego satelita czekała na koniec CAŁEJ syntezy (nawet kilka sekund dla
    dłuższej odpowiedzi), zanim usłyszała pierwszy dźwięk — mimo że i dostawca
    (ElevenLabs), i protokół WS (`tts_start` -> N ramek binarnych -> `tts_end`), i
    odtwarzacz satelity od dawna umiały pracować strumieniowo; tylko nic pomiędzy nimi
    z tego nie korzystało. `synthesize()` zostaje jako wygodna, konkretna metoda
    zbierająca strumień w jeden bufor (mirror `BaseLLMProvider.generate()`) — dla
    wywołujących, którym strumieniowanie jest obojętne (dziś: testy i skrypty)."""

    is_placeholder: bool = False
    """Czy to dostawca dev/testowy, a nie realna synteza. Deklarowane przez sam konkret —
    patrz `BaseSTTProvider.is_placeholder`, ta sama historia zgadywania po nazwie klasy."""

    @abstractmethod
    def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Strumieniuje syntezowane audio (PCM16 mono, parametry próbkowania:
        `shared/voice_protocol.py`) w kolejnych fragmentach, w miarę ich powstawania."""
        ...

    async def synthesize(self, text: str) -> bytes:
        """Sklejone, kompletne audio — zbiera `synthesize_stream()` w jeden bufor."""
        chunks = [chunk async for chunk in self.synthesize_stream(text)]
        return b"".join(chunks)

    async def get_active_provider_class_name(self) -> str:
        """Nazwa klasy faktycznie realizującej zadanie. Domyślnie własna klasa —
        `TTSRouter` (`server.ai.tts`) nadpisuje, by zwrócić nazwę rozwiązanego konkretu."""
        return type(self).__name__

    async def is_active_provider_placeholder(self) -> bool:
        """Czy dostawca faktycznie realizujący zadanie jest placeholderem.
        Mirror `get_active_provider_class_name()` — router nadpisuje, by odpytać konkret."""
        return self.is_placeholder
