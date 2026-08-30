"""Endpoint WS `/voice/{sender_id}` — jedyny punkt styku między gniazdem a kernelem.

Sam cykl życia połączenia (doręczenie, subskrypcja `EventBus`, handshake) mieszka
w `voice/connection.py`; tutaj zostaje wyłącznie montaż endpointu i to, co dzieje się
**wokół** połączenia: wpis do rejestru obecności, zdarzenia connect/disconnect
i gwarantowane sprzątnięcie.
"""

from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, WebSocket
from shared import Event, EventBus, get_logger

from server.agent import AgentEngine
from server.ports.stt import BaseSTTProvider
from server.ports.tts import BaseTTSProvider
from server.ports.wakeword import WakeWordDetector
from server.voice.connection import RegistrationCheck, SettingsLoader, VoiceConnection
from server.voice.events import VoiceEventType
from server.voice.presence import ClientPresenceRegistry

logger = get_logger("regis.voice.gateway")

WakeWordDetectorFactory = Callable[[], WakeWordDetector]

__all__ = [
    "RegistrationCheck",
    "SettingsLoader",
    "VoiceConnection",
    "WakeWordDetectorFactory",
    "create_voice_router",
]


def create_voice_router(
    agent_engine: AgentEngine,
    wakeword_detector_factory: WakeWordDetectorFactory,
    stt_provider: BaseSTTProvider,
    tts_provider: BaseTTSProvider,
    presence: ClientPresenceRegistry,
    settings_loader: SettingsLoader,
    is_registered: RegistrationCheck,
) -> APIRouter:
    """Tworzy router z endpointem WS `/voice/{sender_id}`.

    `wakeword_detector_factory` tworzy nowy, świeży detektor (własny bufor/stan)
    dla każdego połączenia — jedna instancja detektora nie jest bezpieczna do
    współdzielenia między satelitami.

    `presence` (`voice/presence.py`) to współdzielony z routerami REST rejestr żywych
    połączeń: kto jest podłączony, w jakim jest stanie i co zadeklarował w handshake.
    Mechaniczny fakt, zero wiedzy o rejestracji/pokoju — to należy do `World`
    (`docs/manifest.md`, sekcja 5). Wcześniej były to trzy osobne kolekcje wędrujące
    przez sygnatury dwóch fabryk routerów, sprzątane trzema niezależnymi linijkami.

    `is_registered` to bramka: **połączyć się wolno każdemu** (inaczej nowa satelita
    nigdy nie pojawiłaby się na liście "Oczekujący" i nie dałoby się jej zatwierdzić),
    ale odpalenie tury wymaga już zatwierdzenia — sprawdzane w `VoiceSession`.
    """
    router = APIRouter()

    @router.websocket("/voice/{sender_id}")
    async def voice_endpoint(websocket: WebSocket, sender_id: str) -> None:
        await websocket.accept()
        presence.connect(sender_id)
        await _publish(agent_engine.event_bus, VoiceEventType.SATELLITE_CONNECTED, sender_id)
        try:
            connection = VoiceConnection(
                sender_id=sender_id,
                websocket=websocket,
                agent_engine=agent_engine,
                wakeword_detector=wakeword_detector_factory(),
                stt_provider=stt_provider,
                tts_provider=tts_provider,
                settings_loader=settings_loader,
                presence=presence,
                is_registered=is_registered,
            )
            await connection.run()
        finally:
            # Jedno wywołanie sprząta cały ślad po kliencie — stan, możliwości i wpis
            # o połączeniu. Wcześniej były to trzy linijki, z których każda dawała się
            # niezależnie zapomnieć.
            presence.disconnect(sender_id)
            await _publish(agent_engine.event_bus, VoiceEventType.SATELLITE_DISCONNECTED, sender_id)

    return router


async def _publish(event_bus: EventBus, event_type: VoiceEventType, sender_id: str) -> None:
    await event_bus.publish(Event(type=event_type, payload={"sender_id": sender_id}, sender="voice"))
