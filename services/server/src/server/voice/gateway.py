"""WS gateway dla satelit — jedyny punkt styku między fizycznym połączeniem a kernelem.

Zna wyłącznie opaque `sender_id`; nigdy nie importuje ani nie czyta configu
`server.world` (patrz `docs/manifest.md`, sekcja "server/voice/"). Model
doręczenia jest jednokierunkowy: `AgentEngine.start_interaction()` tylko
odpala turę i od razu wraca (`agent/engine.py`) — całe doręczenie odpowiedzi
(własnej albo przekierowanej z innego `sender_id` przez
`ToolResult.redirect_sender_id`) idzie przez ciągłą, per-połączeniową
subskrypcję `EventBus`, aktywną przez cały czas życia gniazda, niezależnie od
tego, czy to połączenie zainicjowało bieżącą turę.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared import Event, EventBus, SatelliteMessageType, ServerMessageType, get_logger

from server.agent import AgentEngine
from server.config import Settings
from server.events import ServerEventType
from server.ports.stt import BaseSTTProvider
from server.ports.tts import BaseTTSProvider
from server.ports.wakeword import WakeWordDetector
from server.voice.events import VoiceEventType
from server.voice.session import VoiceSession

logger = get_logger("regis.voice.gateway")

WakeWordDetectorFactory = Callable[[], WakeWordDetector]
SettingsLoader = Callable[[], Settings]

RegistrationCheck = Callable[[str], Awaitable[bool]]
"""Czy dany `sender_id` jest zatwierdzonym klientem. Wstrzykiwane z `main.py` (gdzie
implementację dostarcza `World`) tym samym wzorcem co `connected_sender_ids` — dzięki
temu `voice/` nadal nie importuje `world/` i nie wie, skąd ta odpowiedź pochodzi."""


class VoiceConnection:
    """Jedno żywe połączenie WS — implementuje `SatelliteLink` (doręczenie) i utrzymuje
    ciągłą subskrypcję `EventBus` po własnym `sender_id`, przez cały czas życia gniazda."""

    def __init__(
        self,
        sender_id: str,
        websocket: WebSocket,
        agent_engine: AgentEngine,
        wakeword_detector: WakeWordDetector,
        stt_provider: BaseSTTProvider,
        tts_provider: BaseTTSProvider,
        settings_loader: SettingsLoader,
        sender_states: dict[str, str],
        pending_capabilities: dict[str, list[str]],
        is_registered: RegistrationCheck,
    ) -> None:
        self.sender_id = sender_id
        self._websocket = websocket
        self._agent_engine = agent_engine
        self._settings_loader = settings_loader
        self._sender_states = sender_states
        self._pending_capabilities = pending_capabilities
        self._text_buffer = ""
        self._speak_task: asyncio.Task[None] | None = None
        self.session = VoiceSession(
            sender_id=sender_id,
            link=self,
            wakeword_detector=wakeword_detector,
            stt_provider=stt_provider,
            tts_provider=tts_provider,
            on_transcript=self._on_transcript,
            publish_event=self._publish_voice_event,
            is_registered=is_registered,
            silence_amplitude_threshold=settings_loader().vad_amplitude_threshold,
        )

    # --------------------------------------------------------------------------
    # Zdarzenia statusu dla dashboardu "Klienci" (Web UI, `GET .../clients/watch`)
    # --------------------------------------------------------------------------

    async def _publish_voice_event(self, event_type: VoiceEventType, payload: dict[str, Any]) -> None:
        """`sender_states` (mirror `connected_sender_ids`, dla `GET .../clients/status`)
        aktualizowany tutaj przy okazji publikacji — jedyne miejsce, w którym stan sesji
        realnie się zmienia, patrz `VoiceSession._set_state`."""
        if event_type == VoiceEventType.SATELLITE_STATE_CHANGED:
            self._sender_states[self.sender_id] = payload["state"]
        await self._agent_engine.event_bus.publish(Event(type=event_type, payload=payload, sender="voice"))

    # --------------------------------------------------------------------------
    # SatelliteLink — używane przez VoiceSession do doręczenia
    # --------------------------------------------------------------------------

    async def send_control(self, message_type: ServerMessageType) -> None:
        await self._websocket.send_text(json.dumps({"type": message_type.value}))

    async def send_audio(self, chunk: bytes) -> None:
        await self._websocket.send_bytes(chunk)

    async def send_error(self, detail: str) -> None:
        await self._websocket.send_text(json.dumps({"type": ServerMessageType.ERROR.value, "detail": detail}))

    async def send_client_config(self, silence_duration_ms: float, amplitude_threshold: int) -> None:
        """Parametry VAD satelity (patrz `Settings.vad_*`) — algorytm zostaje lokalny,
        próg jest centralnie skonfigurowany tutaj. Wysyłane raz, przy handshake."""
        await self._websocket.send_text(
            json.dumps(
                {
                    "type": ServerMessageType.CLIENT_CONFIG.value,
                    "silence_duration_ms": silence_duration_ms,
                    "amplitude_threshold": amplitude_threshold,
                }
            )
        )

    # --------------------------------------------------------------------------
    # Odpalenie tury kernela — jednokierunkowe, "wyślij i zapomnij"
    # --------------------------------------------------------------------------

    def _on_transcript(self, transcript: str) -> None:
        """Sesją satelity jest jej własny `sender_id` — jeden i ten sam przez cały czas
        istnienia klienta. Dlatego to TU, na brzegu kompozycji, wnosimy politykę
        wygaszania historii po bezczynności: kernel nie wie, że rozmawia z satelitą,
        a czat Web UI (`network/routes/chat.py`) nie podaje jej wcale i nie wygasa."""
        try:
            self._agent_engine.start_interaction(
                session_id=self.sender_id,
                prompt=transcript,
                sender_id=self.sender_id,
                session_idle_ttl_seconds=self._settings_loader().satellite_session_idle_ttl_seconds,
            )
        except RuntimeError as err:
            logger.warning(f"Nie odpalono interakcji [sender_id: '{self.sender_id}']: {err}")

    # --------------------------------------------------------------------------
    # Ciągła subskrypcja EventBus — niezależna od tego, kto zainicjował turę
    # --------------------------------------------------------------------------

    async def _on_chunk(self, event: Event[Any]) -> None:
        """Bufor mowy zbiera WYŁĄCZNIE tekst odpowiedzi. Rozumowanie modelu przychodzi tym
        samym kanałem, ale oznaczone `kind: "reasoning"` (patrz `ports/llm.py::ReasoningChunk`)
        — dopóki nie było tego rozróżnienia, satelita czytała na głos cały chain of thought."""
        if event.payload.get("kind") == "reasoning":
            return
        if event.payload.get("target_client_id") == self.sender_id:
            self._text_buffer += event.payload.get("chunk", "")

    async def _on_done(self, event: Event[Any]) -> None:
        """Dwie różne role w jednym handlerze, bo to dwa różne pytania o tę samą turę:

        * jestem ADRESATEM dostawy (`target_client_id`) — mówię zgromadzony tekst;
        * jestem tylko INICJATOREM (`session_id`), a dostawa poszła gdzie indziej
          (`speak_in_room`) — nie mam nic do powiedzenia, ale muszę wyjść z PROCESSING,
          inaczej zostałbym w nim na zawsze, czekając na `tts_start`, którego nigdy nie
          będzie.

        **Każda** gałąź adresata kończy się jawnym wyjściem ze stanu przetwarzania —
        także ta bez tekstu. Dawniej pusta odpowiedź kończyła się gołym `return`, co
        zostawiało sesję w `PROCESSING` na zawsze (satelita z wstrzymanym mikrofonem
        była wtedy trwale głucha aż do restartu).
        """
        payload = event.payload
        if payload.get("target_client_id") == self.sender_id:
            text = self._text_buffer
            self._text_buffer = ""
            if text.strip():
                self._start_speaking(text)
            else:
                await self.session.end_turn_without_speech()
            return
        if payload.get("session_id") == self.sender_id:
            self._text_buffer = ""
            logger.info(f"Tura dostarczona innemu klientowi [sender_id: '{self.sender_id}'] — wracam do nasłuchu.")
            await self.session.reset_to_listening()

    def _start_speaking(self, text: str) -> None:
        """Odpala syntezę POZA handlerem `EventBus`.

        `EventBus.publish()` woła handlery sekwencyjnie i czeka na każdy — trzymanie tu
        `await session.speak(...)` blokowało publikację `CHAT_DONE` do wszystkich
        pozostałych subskrybentów (m.in. kanału SSE Web UI) na cały czas trwania
        odpowiedzi głosowej (synteza + strumieniowe wysyłanie audio), czyli realnie
        kilka sekund nawet przy streamingu TTS (`voice/session.py::speak()`). Referencja
        jest trzymana, bo `asyncio` nie gwarantuje życia zadania, do którego nikt się
        nie odwołuje."""
        task = asyncio.create_task(self.session.speak(text))
        self._speak_task = task

        def _log_failure(finished: "asyncio.Task[None]") -> None:
            if finished.cancelled():
                return
            err = finished.exception()
            if err is not None:
                logger.error(f"Nieobsłużony błąd syntezy [sender_id: '{self.sender_id}']: {err}")

        task.add_done_callback(_log_failure)

    async def _on_error_or_cancelled(self, event: Event[Any]) -> None:
        """Bez tego handlera błąd/anulowanie tury (kernel nigdy nie doszedł do CHAT_DONE
        pod naszym adresem) zostawiłoby `VoiceSession` uwięzioną w PROCESSING na zawsze —
        satelita czekałaby na tts_start, którego nigdy nie będzie."""
        # Błąd/anulowanie dotyczy nas, jeśli jesteśmy adresatem dostawy ALBO inicjatorem
        # tury (mirror `_on_done` — po przekierowaniu nadal musimy wyjść z PROCESSING).
        if self.sender_id not in (event.payload.get("target_client_id"), event.payload.get("session_id")):
            return
        self._text_buffer = ""
        detail = event.payload.get("error", "Przerwano generowanie odpowiedzi.")
        logger.warning(f"Błąd/anulowanie tury [sender_id: '{self.sender_id}']: {detail}")
        await self.send_error(str(detail))
        await self.session.reset_to_listening()

    def _subscribe(self, event_bus: EventBus) -> None:
        event_bus.subscribe(ServerEventType.CHAT_CHUNK, self._on_chunk)
        event_bus.subscribe(ServerEventType.CHAT_DONE, self._on_done)
        event_bus.subscribe(ServerEventType.CHAT_ERROR, self._on_error_or_cancelled)
        event_bus.subscribe(ServerEventType.CHAT_CANCELLED, self._on_error_or_cancelled)

    def _unsubscribe(self, event_bus: EventBus) -> None:
        event_bus.unsubscribe(ServerEventType.CHAT_CHUNK, self._on_chunk)
        event_bus.unsubscribe(ServerEventType.CHAT_DONE, self._on_done)
        event_bus.unsubscribe(ServerEventType.CHAT_ERROR, self._on_error_or_cancelled)
        event_bus.unsubscribe(ServerEventType.CHAT_CANCELLED, self._on_error_or_cancelled)

    # --------------------------------------------------------------------------
    # Cykl życia połączenia
    # --------------------------------------------------------------------------

    async def run(self) -> None:
        self._subscribe(self._agent_engine.event_bus)
        try:
            await self._handshake()
            while True:
                message = await self._websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                frame_bytes = message.get("bytes")
                frame_text = message.get("text")
                if frame_bytes is not None:
                    await self.session.handle_audio_frame(frame_bytes)
                elif frame_text is not None:
                    await self._handle_control_message(frame_text)
        except WebSocketDisconnect:
            logger.info(f"Satelita rozłączona [sender_id: '{self.sender_id}'].")
        finally:
            self._unsubscribe(self._agent_engine.event_bus)

    async def _handshake(self) -> None:
        raw = await self._websocket.receive_text()
        try:
            hello = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Nieprawidłowy handshake JSON [sender_id: '{self.sender_id}']: {raw!r}.")
            return
        if hello.get("type") != SatelliteMessageType.HELLO.value:
            logger.warning(f"Oczekiwano handshake 'hello' [sender_id: '{self.sender_id}'], dostano: {hello}.")
            return
        # Deklarowane możliwości nie są już tylko logowane — trafiają do współdzielonego
        # rejestru, z którego czyta `GET /api/v1/voice/connected`, żeby rejestracja z Web UI
        # zapisała w World PRAWDZIWE capabilities klienta zamiast je zgadywać.
        raw_capabilities = hello.get("capabilities")
        capabilities = [str(c) for c in raw_capabilities] if isinstance(raw_capabilities, list) else []
        self._pending_capabilities[self.sender_id] = capabilities
        logger.info(f"Satelita połączona [sender_id: '{self.sender_id}'], możliwości: {capabilities}.")

        settings = self._settings_loader()
        await self.send_client_config(settings.vad_silence_duration_ms, settings.vad_amplitude_threshold)

    async def _handle_control_message(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning(f"Nieprawidłowa ramka JSON od satelity [sender_id: '{self.sender_id}']: {raw!r}.")
            return
        msg_type = data.get("type")
        if msg_type == SatelliteMessageType.UTTERANCE_END.value:
            await self.session.handle_utterance_end()
        elif msg_type == SatelliteMessageType.PLAYBACK_DONE.value:
            await self.session.handle_playback_done()
        else:
            logger.warning(f"Nieznany typ wiadomości od satelity [sender_id: '{self.sender_id}']: {msg_type!r}.")


def create_voice_router(
    agent_engine: AgentEngine,
    wakeword_detector_factory: WakeWordDetectorFactory,
    stt_provider: BaseSTTProvider,
    tts_provider: BaseTTSProvider,
    connected_sender_ids: set[str],
    settings_loader: SettingsLoader,
    sender_states: dict[str, str],
    pending_capabilities: dict[str, list[str]],
    is_registered: RegistrationCheck,
) -> APIRouter:
    """Tworzy router z endpointem WS `/voice/{sender_id}`.

    `wakeword_detector_factory` tworzy nowy, świeży detektor (własny bufor/stan)
    dla każdego połączenia — jedna instancja detektora nie jest bezpieczna do
    współdzielenia między satelitami.

    `connected_sender_ids` to współdzielony (z `create_voice_status_router`,
    `routes.py`) zbiór `sender_id` z aktualnie żywym połączeniem WS — mechaniczny
    fakt, zero wiedzy o rejestracji/pokoju (to należy do `World`, patrz
    `docs/manifest.md` sekcja 5). Pozwala Web UI (panel Nadawcy) pokazać
    podłączone, ale jeszcze niezarejestrowane satelity. Zwykły `set`, bez
    locka — jeden wątek asyncio, mutacje bezpieczne.

    `sender_states` (mirror `connected_sender_ids`) trzyma ostatnio znany
    `SessionState.name` per `sender_id` — snapshot do hydratacji dashboardu
    "Klienci" przy pierwszym załadowaniu strony (`GET .../clients/status`),
    dalsze zmiany dochodzą już tylko przez `GET .../clients/watch` (SSE).

    `pending_capabilities` (ten sam wzorzec) trzyma możliwości zadeklarowane w
    handshake — Web UI czyta je przy rejestracji, żeby zapisać w World realne
    capabilities zamiast zgadywać typ klienta.

    `is_registered` to bramka: **połączyć się wolno każdemu** (inaczej nowa satelita
    nigdy nie pojawiłaby się na liście "Oczekujący" i nie dałoby się jej zatwierdzić),
    ale odpalenie tury wymaga już zatwierdzenia — sprawdzane w `VoiceSession`.
    """
    router = APIRouter()

    @router.websocket("/voice/{sender_id}")
    async def voice_endpoint(websocket: WebSocket, sender_id: str) -> None:
        await websocket.accept()
        connected_sender_ids.add(sender_id)
        await agent_engine.event_bus.publish(
            Event(type=VoiceEventType.SATELLITE_CONNECTED, payload={"sender_id": sender_id}, sender="voice")
        )
        try:
            connection = VoiceConnection(
                sender_id=sender_id,
                websocket=websocket,
                agent_engine=agent_engine,
                wakeword_detector=wakeword_detector_factory(),
                stt_provider=stt_provider,
                tts_provider=tts_provider,
                settings_loader=settings_loader,
                sender_states=sender_states,
                pending_capabilities=pending_capabilities,
                is_registered=is_registered,
            )
            await connection.run()
        finally:
            connected_sender_ids.discard(sender_id)
            sender_states.pop(sender_id, None)
            pending_capabilities.pop(sender_id, None)
            await agent_engine.event_bus.publish(
                Event(type=VoiceEventType.SATELLITE_DISCONNECTED, payload={"sender_id": sender_id}, sender="voice")
            )

    return router
