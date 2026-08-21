"""Router REST domeny `server.voice` — ścieżki WZGLĘDNE.

Montowany osobno od WS gatewaya (`gateway.py`, prefiks `/ws`), pod stałym
prefiksem `/api/v1/voice`, analogicznie do `/api/v1/world`.

`GET /status` — wyłącznie odczyt (nazwy klas aktywnych providerów, przez
`get_active_provider_class_name()` — dla `STTRouter`/`TTSRouter` rozwiązuje
aktualny konkret na żywo, patrz `server.ai.stt`/`server.ai.tts`).

`GET /connected` — `sender_id` z aktualnie żywym połączeniem WS
(`connected_sender_ids`, wypełniany przez `gateway.py`, wstrzykiwany z
`main.py` jako współdzielony `set`) — pozwala Web UI (panel Nadawcy, Świat)
pokazać satelity podłączone, ale jeszcze niezarejestrowane w `World`.

CRUD dostawców STT/TTS (`GET/POST/PUT/DELETE /stt/providers*`, `.../tts/providers*`)
i shim kompatybilności `GET/PUT /providers/config` żyją osobno, w
`voice/provider_routes.py` (mirror podziału `network/routes/health.py` vs
`network/routes/providers.py` po stronie LLM).
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


class ConnectedSendersDTO(BaseModel):
    """`sender_id` z aktualnie żywym połączeniem WS — mechaniczny fakt (`gateway.py`),
    zero wiedzy o rejestracji/pokoju (to należy do `World`). Pozwala Web UI (panel
    Nadawcy, Świat) pokazać podłączone, ale jeszcze niezarejestrowane satelity."""

    sender_ids: list[str] = Field(..., description="Posortowana lista sender_id z żywym połączeniem WS")


def create_voice_status_router(
    stt_provider: BaseSTTProvider,
    tts_provider: BaseTTSProvider,
    wakeword_detector_class_name: str,
    connected_sender_ids: set[str],
) -> APIRouter:
    """Tworzy router statusu — providerzy/nazwa detektora wstrzykiwane z `main.py`."""
    router = APIRouter()

    @router.get("/status", response_model=VoiceStatusDTO, tags=["Voice"])
    async def get_status() -> VoiceStatusDTO:
        stt_name = await stt_provider.get_active_provider_class_name()
        tts_name = await tts_provider.get_active_provider_class_name()
        return VoiceStatusDTO(
            stt_provider=stt_name,
            tts_provider=tts_name,
            wakeword_detector=wakeword_detector_class_name,
            is_production_ready=not any(name.startswith("Mock") for name in (stt_name, tts_name)),
        )

    @router.get("/connected", response_model=ConnectedSendersDTO, tags=["Voice"])
    async def get_connected() -> ConnectedSendersDTO:
        return ConnectedSendersDTO(sender_ids=sorted(connected_sender_ids))

    return router
