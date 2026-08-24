"""TTS — synteza tekst -> audio. `BaseTTSProvider` to mirror `BaseLLMProvider`
(`agent/llm.py`). Konkretni dostawcy (`ElevenLabsTTSProvider`, `MockTTSProvider`)
oraz logika wyboru (`TTSRegistry`/`TTSFactory`) mieszkają w `server.ai.tts` — ten
moduł trzyma wyłącznie protokół, dokładnie jak Kernel trzyma `BaseLLMProvider`.
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
    wywołujących, którym strumieniowanie jest obojętne (np. `check_health`)."""

    @abstractmethod
    def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Strumieniuje syntezowane audio (PCM16 mono, parametry próbkowania:
        `voice/protocol.py`) w kolejnych fragmentach, w miarę ich powstawania."""
        ...

    async def synthesize(self, text: str) -> bytes:
        """Sklejone, kompletne audio — zbiera `synthesize_stream()` w jeden bufor."""
        chunks = [chunk async for chunk in self.synthesize_stream(text)]
        return b"".join(chunks)

    async def get_active_provider_class_name(self) -> str:
        """Nazwa klasy faktycznie realizującej zadanie. Domyślnie własna klasa —
        `TTSRouter` (`server.ai.tts`) nadpisuje, by zwrócić nazwę rozwiązanego konkretu."""
        return type(self).__name__
