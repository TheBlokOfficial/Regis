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

import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from shared import ConfigStore, Event, EventBus

from server.config import Settings
from server.ports.stt import BaseSTTProvider
from server.ports.tts import BaseTTSProvider
from server.voice.events import VoiceEventType


class VoiceStatusDTO(BaseModel):
    """Aktualna konfiguracja pipeline'u głosowego — nazwy klas aktywnych providerów."""

    stt_provider: str = Field(..., description="Nazwa klasy aktywnego dostawcy STT")
    tts_provider: str = Field(..., description="Nazwa klasy aktywnego dostawcy TTS")
    wakeword_detector: str = Field(..., description="Nazwa klasy detektora wake-word")
    is_production_ready: bool = Field(
        ...,
        description=(
            "False dopóki którykolwiek element pipeline'u jest dev-providerem: Mock* dla STT/TTS "
            "albo ThresholdEnergyWakeWordDetector (placeholder reagujący na głośność, nie na słowo)"
        ),
    )


class ConnectedSenderDTO(BaseModel):
    """Jedno żywe połączenie WS wraz z możliwościami zadeklarowanymi w handshake."""

    sender_id: str = Field(..., description="Opaque identyfikator nadawcy")
    capabilities: list[str] = Field(
        default_factory=list, description="Możliwości z handshake (np. mic, speaker) — surowe, niezwalidowane"
    )


class ConnectedSendersDTO(BaseModel):
    """Klienci z aktualnie żywym połączeniem WS — mechaniczny fakt (`gateway.py`),
    zero wiedzy o rejestracji/pokoju (to należy do `World`). Pozwala Web UI pokazać
    podłączone, ale jeszcze niezatwierdzone satelity i zarejestrować je z ICH
    prawdziwymi capabilities zamiast zgadywanymi.

    `sender_ids` zostaje obok `senders` jako pole zgodnościowe dla istniejących
    konsumentów (ta sama lista, tylko same identyfikatory)."""

    sender_ids: list[str] = Field(..., description="Posortowana lista sender_id z żywym połączeniem WS")
    senders: list[ConnectedSenderDTO] = Field(default_factory=list, description="To samo, wzbogacone o capabilities")


class VoiceClientConfigDTO(BaseModel):
    """Konfiguracja "klientów" głosowych — próg wake-worda (100% serwerowa detekcja,
    patrz `ai/wakeword/detectors.py`) i parametry VAD (algorytm lokalny na satelicie, próg
    centralnie skonfigurowany tutaj i wysyłany przy handshake, patrz `gateway.py`
    `send_client_config`/`ServerMessageType.CLIENT_CONFIG`)."""

    wakeword_threshold: float = Field(..., ge=0.0, le=1.0, description="Próg pewności detekcji wake-word (0-1)")
    vad_silence_duration_ms: float = Field(..., gt=0.0, description="Czas ciągłej ciszy (ms) uznawany za koniec wypowiedzi")
    vad_amplitude_threshold: int = Field(..., ge=0, description="Próg amplitudy PCM16 poniżej którego ramka liczy się jako cisza")


class ClientStatusSnapshotDTO(BaseModel):
    """Snapshot `SessionState.name` per `sender_id` aktualnie połączonych satelitów —
    hydratacja dashboardu "Klienci" przy pierwszym załadowaniu strony; dalsze zmiany
    dochodzą już tylko przez `GET .../clients/watch` (SSE, patrz niżej)."""

    states: dict[str, str] = Field(..., description="sender_id -> SessionState.name")


def create_voice_status_router(
    stt_provider: BaseSTTProvider,
    tts_provider: BaseTTSProvider,
    wakeword_detector_class_name: str,
    connected_sender_ids: set[str],
    config_store: ConfigStore[Settings],
    sender_states: dict[str, str],
    event_bus: EventBus,
    pending_capabilities: dict[str, list[str]],
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
            # Placeholder wake-worda liczy się tak samo jak Mock STT/TTS — jest
            # dev-providerem wprost wg własnego docstringu (`ai/wakeword/detectors.py`) i
            # reaguje na sekwencję głośnych ramek, nie na słowo. Bez tego
            # `is_production_ready` mogło zwrócić True dla pipeline'u, który nigdy
            # nie rozpozna "Regis", bo model .onnx się nie załadował.
            is_production_ready=(
                not any(name.startswith("Mock") for name in (stt_name, tts_name))
                and wakeword_detector_class_name != "ThresholdEnergyWakeWordDetector"
            ),
        )

    @router.get("/connected", response_model=ConnectedSendersDTO, tags=["Voice"])
    async def get_connected() -> ConnectedSendersDTO:
        ordered = sorted(connected_sender_ids)
        return ConnectedSendersDTO(
            sender_ids=ordered,
            senders=[
                ConnectedSenderDTO(sender_id=sid, capabilities=pending_capabilities.get(sid, [])) for sid in ordered
            ],
        )

    @router.get("/client-config", response_model=VoiceClientConfigDTO, tags=["Voice"])
    async def get_client_config() -> VoiceClientConfigDTO:
        settings = config_store.load()
        return VoiceClientConfigDTO(
            wakeword_threshold=settings.wakeword_threshold,
            vad_silence_duration_ms=settings.vad_silence_duration_ms,
            vad_amplitude_threshold=settings.vad_amplitude_threshold,
        )

    @router.put("/client-config", response_model=VoiceClientConfigDTO, tags=["Voice"])
    async def update_client_config(req: VoiceClientConfigDTO) -> VoiceClientConfigDTO:
        current = config_store.load()
        updated = current.model_copy(
            update={
                "wakeword_threshold": req.wakeword_threshold,
                "vad_silence_duration_ms": req.vad_silence_duration_ms,
                "vad_amplitude_threshold": req.vad_amplitude_threshold,
            }
        )
        config_store.save(updated)
        return req

    @router.get("/clients/status", response_model=ClientStatusSnapshotDTO, tags=["Voice"])
    async def get_clients_status() -> ClientStatusSnapshotDTO:
        return ClientStatusSnapshotDTO(states=dict(sender_states))

    @router.get("/clients/watch", tags=["Voice"])
    async def watch_clients() -> StreamingResponse:
        """Pasywna, długożyjąca subskrypcja zdarzeń satelitów (SSE) — mirror
        `AgentEngine.watch_session()`/`GET .../chat/sessions/{id}/watch` z domeny chat,
        tyle że **globalna** (jeden strumień dla wszystkich `sender_id` naraz, bo
        dashboard "Klienci" pokazuje ich wszystkich jednocześnie). Nigdy się nie kończy
        sama — obserwator (karta przeglądarki) decyduje, kiedy przestać czytać."""

        async def event_generator():
            async for event in watch_voice_events(event_bus):
                yield f"data: {json.dumps({**event.payload, 'type': event.type})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    return router


async def watch_voice_events(event_bus: EventBus):
    """Pasywna subskrypcja czterech `VoiceEventType` na `event_bus` — wydzielona z
    `watch_clients()` endpointu, żeby testować mechanizm subskrypcji bezpośrednio
    (mirror `AgentEngine.watch_session()`, testowalnej bez HTTP/SSE). Nigdy się nie
    kończy sama; kończy się dopiero gdy wywołujący przerwie iterację (rozłączenie SSE)."""
    queue: asyncio.Queue[Event] = asyncio.Queue()

    async def on_event(event: Event) -> None:
        await queue.put(event)

    event_types = (
        VoiceEventType.SATELLITE_CONNECTED,
        VoiceEventType.SATELLITE_DISCONNECTED,
        VoiceEventType.SATELLITE_STATE_CHANGED,
        VoiceEventType.SATELLITE_WAKE_WORD_DETECTED,
    )
    for event_type in event_types:
        event_bus.subscribe(event_type, on_event)

    try:
        while True:
            yield await queue.get()
    finally:
        for event_type in event_types:
            event_bus.unsubscribe(event_type, on_event)
