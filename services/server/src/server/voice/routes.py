"""Router REST statusu `server.voice` — ścieżki WZGLĘDNE.

Montowany osobno od WS gatewaya (`gateway.py`, prefiks `/ws`), pod stałym
prefiksem `/api/v1/voice`, analogicznie do `/api/v1/world`. Wyłącznie odczyt —
dziś nie ma żadnego rejestru instancji STT/TTS (jeden, zahardkodowany dev-
provider każdego rodzaju w `main.py`), więc panel VoiceConfig w Web UI
pokazuje wyłącznie aktualną konfigurację, bez CRUD (YAGNI — brak drugiego,
realnego providera w ręku, patrz `docs/manifest.md`).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from server.voice.stt import BaseSTTProvider
from server.voice.tts import BaseTTSProvider


class VoiceStatusDTO(BaseModel):
    """Aktualna konfiguracja pipeline'u głosowego — nazwy klas aktywnych providerów."""

    stt_provider: str = Field(..., description="Nazwa klasy aktywnego dostawcy STT")
    tts_provider: str = Field(..., description="Nazwa klasy aktywnego dostawcy TTS")
    wakeword_detector: str = Field(..., description="Nazwa klasy detektora wake-word")
    is_production_ready: bool = Field(
        ..., description="False dopóki którykolwiek z providerów jest dev-providerem (Mock*)"
    )


def create_voice_status_router(
    stt_provider: BaseSTTProvider,
    tts_provider: BaseTTSProvider,
    wakeword_detector_class_name: str,
) -> APIRouter:
    """Tworzy router statusu — providerzy/nazwa detektora wstrzykiwane z `main.py`."""
    router = APIRouter()

    @router.get("/status", response_model=VoiceStatusDTO, tags=["Voice"])
    async def get_status() -> VoiceStatusDTO:
        stt_name = type(stt_provider).__name__
        tts_name = type(tts_provider).__name__
        return VoiceStatusDTO(
            stt_provider=stt_name,
            tts_provider=tts_name,
            wakeword_detector=wakeword_detector_class_name,
            is_production_ready=not any(name.startswith("Mock") for name in (stt_name, tts_name)),
        )

    return router
