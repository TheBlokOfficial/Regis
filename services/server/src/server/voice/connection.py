"""Jedno żywe połączenie WS satelity — doręczenie i ciągła subskrypcja `EventBus`.

Wydzielone z `gateway.py`, w którym mieszkało razem z endpointem, ręcznym kodowaniem
JSON-a i fabryką routera. Endpoint zostaje tam; tutaj jest wyłącznie to, co dzieje się
**w trakcie** życia gniazda.

Zna wyłącznie opaque `sender_id`; nigdy nie importuje ani nie czyta configu
`server.world` (patrz `docs/manifest.md`, sekcja "server/voice/"). Model doręczenia
jest jednokierunkowy: `AgentEngine.start_interaction()` tylko odpala turę i od razu
wraca (`agent/engine.py`) — całe doręczenie odpowiedzi (własnej albo przekierowanej
z innego `sender_id` przez `ToolResult.redirect_sender_id`) idzie przez ciągłą,
per-połączeniową subskrypcję `EventBus`, aktywną przez cały czas życia gniazda,
niezależnie od tego, czy to połączenie zainicjowało bieżącą turę.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect
from shared import (
    ClientConfigFrame,
    ErrorFrame,
    Event,
    EventBus,
    HelloFrame,
    PlaybackDoneFrame,
    ServerMessageType,
    UtteranceEndFrame,
    decode_satellite_frame,
    encode_frame,
    get_logger,
    server_control_frame,
)

from server.agent import AgentEngine
from server.config import Settings
from server.events import ServerEventType
from server.ports.stt import BaseSTTProvider
from server.ports.tts import BaseTTSProvider
from server.ports.wakeword import WakeWordDetector
from server.voice.events import VoiceEventType
from server.voice.presence import ClientPresenceRegistry
from server.voice.session import VoiceSession

logger = get_logger("regis.voice.connection")

SettingsLoader = Callable[[], Settings]

RegistrationCheck = Callable[[str], Awaitable[bool]]
"""Czy dany `sender_id` jest zatwierdzonym klientem. Wstrzykiwane z `main.py` (gdzie
implementację dostarcza `World`) tym samym wzorcem co rejestr obecności — dzięki temu
`voice/` nadal nie importuje `world/` i nie wie, skąd ta odpowiedź pochodzi."""


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
        presence: ClientPresenceRegistry,
        is_registered: RegistrationCheck,
    ) -> None:
        self.sender_id = sender_id
        self._websocket = websocket
        self._agent_engine = agent_engine
        self._settings_loader = settings_loader
        self._presence = presence
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
        """Rejestr obecności aktualizowany tutaj przy okazji publikacji — jedyne miejsce,
        w którym stan sesji realnie się zmienia, patrz `VoiceSession._set_state`."""
        if event_type == VoiceEventType.SATELLITE_STATE_CHANGED:
            self._presence.set_state(self.sender_id, payload["state"])
        await self._agent_engine.event_bus.publish(Event(type=event_type, payload=payload, sender="voice"))

    # --------------------------------------------------------------------------
    # SatelliteLink — używane przez VoiceSession do doręczenia
    # --------------------------------------------------------------------------

    async def send_control(self, message_type: ServerMessageType) -> None:
        await self._websocket.send_text(encode_frame(server_control_frame(message_type)))

    async def send_audio(self, chunk: bytes) -> None:
        await self._websocket.send_bytes(chunk)

    async def send_error(self, detail: str) -> None:
        await self._websocket.send_text(encode_frame(ErrorFrame(detail=detail)))

    async def send_client_config(self, silence_duration_ms: float, amplitude_threshold: int) -> None:
        """Parametry VAD satelity (patrz `Settings.vad_*`) — algorytm zostaje lokalny,
        próg jest centralnie skonfigurowany tutaj. Wysyłane raz, przy handshake."""
        await self._websocket.send_text(
            encode_frame(
                ClientConfigFrame(
                    silence_duration_ms=silence_duration_ms,
                    amplitude_threshold=amplitude_threshold,
                )
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
        frame = decode_satellite_frame(raw)
        if not isinstance(frame, HelloFrame):
            logger.warning(f"Oczekiwano handshake 'hello' [sender_id: '{self.sender_id}'], dostano: {raw!r}.")
            return
        # Deklarowane możliwości nie są już tylko logowane — trafiają do rejestru
        # obecności, z którego czyta `GET /api/v1/voice/connected`, żeby rejestracja
        # z Web UI zapisała w World PRAWDZIWE capabilities klienta zamiast je zgadywać.
        self._presence.declare_capabilities(self.sender_id, frame.capabilities)
        logger.info(f"Satelita połączona [sender_id: '{self.sender_id}'], możliwości: {frame.capabilities}.")

        settings = self._settings_loader()
        await self.send_client_config(settings.vad_silence_duration_ms, settings.vad_amplitude_threshold)

    async def _handle_control_message(self, raw: str) -> None:
        frame = decode_satellite_frame(raw)
        if isinstance(frame, UtteranceEndFrame):
            await self.session.handle_utterance_end()
        elif isinstance(frame, PlaybackDoneFrame):
            await self.session.handle_playback_done()
        elif frame is None:
            # Kodek zalogował już szczegół; tutaj dokładamy tożsamość nadawcy.
            logger.warning(f"Odrzucono ramkę od satelity [sender_id: '{self.sender_id}'].")
        else:
            logger.warning(f"Nieobsłużona ramka od satelity [sender_id: '{self.sender_id}']: {frame!r}.")
