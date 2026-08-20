"""Router REST domeny `server.voice` — ścieżki WZGLĘDNE.

Montowany osobno od WS gatewaya (`gateway.py`, prefiks `/ws`), pod stałym
prefiksem `/api/v1/voice`, analogicznie do `/api/v1/world`.

`GET /status` — wyłącznie odczyt (nazwy klas aktywnych providerów). Config
`GET/PUT /providers/config` (Groq/ElevenLabs) — dodany, gdy pojawił się
konkretny, realny provider w ręku (wcześniej ta zakładka była świadomym
placeholderem, YAGNI). **Ważne**: providery STT/TTS są budowane raz przy
starcie serwera (`main.py`) i wstrzykiwane do `VoiceConnection` jako gotowe
instancje — zmiana klucza/modelu przez `PUT` zapisuje się na dysk, ale zaczyna
obowiązywać dopiero po restarcie serwera (ten sam kompromis co reszta configu
bez hot-reloadu w tym projekcie, patrz `docs/onboarding.md` sekcja 4).

`GET /connected` — `sender_id` z aktualnie żywym połączeniem WS
(`connected_sender_ids`, wypełniany przez `gateway.py`, wstrzykiwany z
`main.py` jako współdzielony `set`) — pozwala Web UI (panel Nadawcy, Świat)
pokazać satelity podłączone, ale jeszcze niezarejestrowane w `World`.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from server.voice.config import (
    VoiceProvidersConfig,
    load_voice_providers_config,
    save_voice_providers_config,
)
from server.voice.dto import UpdateVoiceProvidersConfigRequest, VoiceProvidersConfigDTO
from server.voice.stt import BaseSTTProvider
from server.voice.tts import BaseTTSProvider


def _mask_key(key: str) -> str:
    """Maskuje klucz API do ostatnich 4 widocznych znaków (mirror `_mask_token`
    w `world/routes.py` — brak wspólnego miejsca na tak małą funkcję, YAGNI)."""
    if not key:
        return key
    visible = key[-4:] if len(key) > 4 else ""
    return f"{'•' * (len(key) - len(visible))}{visible}"


def _to_config_dto(config: VoiceProvidersConfig) -> VoiceProvidersConfigDTO:
    return VoiceProvidersConfigDTO(
        groq_api_key=_mask_key(config.groq_api_key),
        groq_stt_model=config.groq_stt_model,
        elevenlabs_api_key=_mask_key(config.elevenlabs_api_key),
        elevenlabs_voice_id=config.elevenlabs_voice_id,
        elevenlabs_model_id=config.elevenlabs_model_id,
    )


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
        stt_name = type(stt_provider).__name__
        tts_name = type(tts_provider).__name__
        return VoiceStatusDTO(
            stt_provider=stt_name,
            tts_provider=tts_name,
            wakeword_detector=wakeword_detector_class_name,
            is_production_ready=not any(name.startswith("Mock") for name in (stt_name, tts_name)),
        )

    @router.get("/connected", response_model=ConnectedSendersDTO, tags=["Voice"])
    async def get_connected() -> ConnectedSendersDTO:
        return ConnectedSendersDTO(sender_ids=sorted(connected_sender_ids))

    @router.get("/providers/config", response_model=VoiceProvidersConfigDTO, tags=["Voice"])
    async def get_providers_config() -> VoiceProvidersConfigDTO:
        return _to_config_dto(await load_voice_providers_config())

    @router.put("/providers/config", response_model=VoiceProvidersConfigDTO, tags=["Voice"])
    async def update_providers_config(req: UpdateVoiceProvidersConfigRequest) -> VoiceProvidersConfigDTO:
        current = await load_voice_providers_config()
        updated = current.model_copy(
            update={
                "groq_api_key": req.groq_api_key if req.groq_api_key else current.groq_api_key,
                "groq_stt_model": req.groq_stt_model,
                "elevenlabs_api_key": req.elevenlabs_api_key if req.elevenlabs_api_key else current.elevenlabs_api_key,
                "elevenlabs_voice_id": req.elevenlabs_voice_id,
                "elevenlabs_model_id": req.elevenlabs_model_id,
            }
        )
        await save_voice_providers_config(updated)
        return _to_config_dto(updated)

    return router
