"""Automat stanu jednej rozmowy głosowej.

```text
LISTENING_WAKEWORD -> (wake-word) -> RECORDING_UTTERANCE
    -> (utterance_end) -> PROCESSING (STT -> kernel)
    -> SYNTHESIZING (TTS) -> SPEAKING -> (playback_done) -> LISTENING_WAKEWORD
```

Każde wyjście z `PROCESSING`/`SYNTHESIZING`/`SPEAKING` musi kończyć się powrotem do
nasłuchu — także ścieżki bez mowy (`end_turn_without_speech`) i błędne (`reset_to_listening`).
Satelita wstrzymuje mikrofon poza nasłuchem, więc każdy stan bez wyjścia to trwała głuchota.

Czysty automat treści/stanu — zero wiedzy o WebSocket czy EventBus. Doręczenie
(`SatelliteLink`) i odpalenie tury kernela (`on_transcript`) są wstrzykiwane,
żeby dało się testować bez prawdziwego gniazda ani prawdziwego `AgentEngine`
(patrz `gateway.py`, gdzie żyje realna implementacja `SatelliteLink`).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Any, Awaitable, Callable, Protocol

from shared import ServerMessageType, get_logger

from server.voice.events import VoiceEventType
from server.voice.stt import BaseSTTProvider
from server.voice.tts import BaseTTSProvider
from server.voice.wakeword import WakeWordDetector

logger = get_logger("regis.voice.session")

EventPublisher = Callable[[VoiceEventType, dict[str, Any]], Awaitable[None]]

RegistrationCheck = Callable[[str], Awaitable[bool]]
"""Czy ten `sender_id` jest zatwierdzonym klientem — wstrzykiwane (patrz `gateway.py`),
nigdy sprawdzane tu bezpośrednio: automat stanu nie wie, gdzie mieszka rejestr."""


class SessionState(Enum):
    LISTENING_WAKEWORD = auto()
    RECORDING_UTTERANCE = auto()
    PROCESSING = auto()
    SYNTHESIZING = auto()
    SPEAKING = auto()


class SatelliteLink(Protocol):
    """Minimalny kontrakt doręczenia do fizycznego połączenia — implementowany przez
    `VoiceConnection` (`gateway.py`)."""

    async def send_control(self, message_type: ServerMessageType) -> None: ...

    async def send_audio(self, chunk: bytes) -> None: ...

    async def send_error(self, detail: str) -> None: ...


class VoiceSession:
    """Automat stanu jednej rozmowy — jedna instancja per żywe połączenie WS."""

    def __init__(
        self,
        sender_id: str,
        link: SatelliteLink,
        wakeword_detector: WakeWordDetector,
        stt_provider: BaseSTTProvider,
        tts_provider: BaseTTSProvider,
        on_transcript: Callable[[str], None],
        publish_event: EventPublisher,
        is_registered: RegistrationCheck | None = None,
    ) -> None:
        self.sender_id = sender_id
        self.state = SessionState.LISTENING_WAKEWORD
        self._link = link
        self._wakeword_detector = wakeword_detector
        self._stt_provider = stt_provider
        self._tts_provider = tts_provider
        self._on_transcript = on_transcript
        self._publish_event = publish_event
        self._is_registered = is_registered
        self._utterance_buffer = bytearray()

    async def _set_state(self, state: SessionState) -> None:
        """Zmienia stan i rozgłasza `SATELLITE_STATE_CHANGED` — jedyne miejsce, w którym
        `self.state` się zmienia, żeby dashboard "Klienci" (Web UI) zawsze widział każdą
        zmianę na żywo, bez trwałego zapisu (czysto efemeryczne, mirror `sender_states`
        w `gateway.py`)."""
        self.state = state
        await self._publish_event(
            VoiceEventType.SATELLITE_STATE_CHANGED, {"sender_id": self.sender_id, "state": state.name}
        )

    async def handle_audio_frame(self, chunk: bytes) -> None:
        """Ramka binarna PCM od satelity — znaczenie zależy od bieżącego stanu."""
        if self.state == SessionState.LISTENING_WAKEWORD:
            if self._wakeword_detector.process(chunk):
                logger.info(f"Wake-word wykryty [sender_id: '{self.sender_id}'].")
                await self._publish_event(
                    VoiceEventType.SATELLITE_WAKE_WORD_DETECTED,
                    {"sender_id": self.sender_id, "score": self._wakeword_detector.last_score},
                )
                await self._set_state(SessionState.RECORDING_UTTERANCE)
                self._utterance_buffer.clear()
                await self._link.send_control(ServerMessageType.WAKE_DETECTED)
            return
        if self.state == SessionState.RECORDING_UTTERANCE:
            self._utterance_buffer.extend(chunk)
            return
        # PROCESSING/SPEAKING: satelita nie powinna strumieniować mikrofonu (uniknięcie
        # nagrywania własnego odtwarzania bez echo-cancellation) — ramki po cichu ignorowane.

    async def handle_utterance_end(self) -> None:
        """Satelita zgłosiła koniec wypowiedzi (własny VAD, 1.5s ciszy)."""
        if self.state != SessionState.RECORDING_UTTERANCE:
            logger.warning(f"utterance_end poza stanem nagrywania [sender_id: '{self.sender_id}'] — zignorowano.")
            return
        await self._link.send_control(ServerMessageType.PLAY_STOP_TONE)
        await self._set_state(SessionState.PROCESSING)

        # Bramka rejestracji — połączyć się wolno każdemu (żeby dało się zobaczyć klienta
        # na liście "Oczekujący" i go zatwierdzić), ale turę odpala dopiero zatwierdzony.
        # Sprawdzane TUTAJ, nie przy handshake: nagranie już powstało, więc odmowa jest
        # czytelna dla użytkownika (usłyszy komunikat), a nie objawia się cichym brakiem
        # reakcji na wake-word.
        if self._is_registered is not None and not await self._is_registered(self.sender_id):
            logger.warning(f"Odrzucono turę niezarejestrowanego klienta [sender_id: '{self.sender_id}'].")
            await self._link.send_error("Ten klient nie jest jeszcze zarejestrowany — zatwierdź go w zakładce Klienci.")
            await self.reset_to_listening()
            return

        audio = bytes(self._utterance_buffer)
        self._utterance_buffer.clear()
        try:
            transcript = await self._stt_provider.transcribe(audio)
        except Exception as err:
            # Surowa treść wyjątku (może zdradzać szczegóły dostawcy) wyłącznie do logów —
            # ten sam wzorzec sanityzacji co `agent/engine.py::_generate_in_background`.
            logger.error(f"Transkrypcja STT nie powiodła się [sender_id: '{self.sender_id}']: {err}")
            await self._link.send_error("STT nieskonfigurowany lub niedostępny — spróbuj ponownie później.")
            await self.reset_to_listening()
            return
        logger.info(f"Transkrypcja [sender_id: '{self.sender_id}']: '{transcript}'")
        self._on_transcript(transcript)
        # Pozostajemy w PROCESSING — powrót do LISTENING_WAKEWORD następuje dopiero
        # po realnym odtworzeniu odpowiedzi (`speak()` -> `handle_playback_done()`),
        # sterowanym z zewnątrz przez gateway (odbiór CHAT_DONE z EventBus).

    async def speak(self, text: str) -> None:
        """Syntezuje i odtwarza odpowiedź — wołane przez gateway po odebraniu CHAT_DONE.

        `SYNTHESIZING` i `SPEAKING` to dwa różne stany, bo to dwa różne oczekiwania:
        pierwsze trwa tyle, ile zapytanie do dostawcy TTS, drugie tyle, ile realne
        odtwarzanie u klienta. Dopóki oba nazywały się `SPEAKING`, dashboard pokazywał
        "Odpowiada" także wtedy, gdy nic jeszcze nie grało — i nie dało się odróżnić
        wolnej syntezy od zawieszonego odtwarzania.

        Wyjątek dostawcy TTS **musi** być złapany tutaj: `speak()` jest wołane z handlera
        `EventBus`, a ten połyka wyjątki (`shared/event_bus.py::publish`), więc bez tego
        sesja zostawałaby w `SPEAKING` na zawsze, a satelita — z wstrzymanym mikrofonem.
        """
        await self._set_state(SessionState.SYNTHESIZING)
        try:
            audio = await self._tts_provider.synthesize(text)
        except Exception as err:
            # Sanityzacja jak wszędzie indziej: szczegół dostawcy tylko do logu.
            logger.error(f"Synteza mowy nie powiodła się [sender_id: '{self.sender_id}']: {err}")
            await self._link.send_error("Synteza mowy nieskonfigurowana lub niedostępna.")
            await self.reset_to_listening()
            return

        if not audio:
            logger.warning(f"Dostawca TTS zwrócił puste audio [sender_id: '{self.sender_id}'].")
            await self.end_turn_without_speech()
            return

        await self._set_state(SessionState.SPEAKING)
        await self._link.send_control(ServerMessageType.TTS_START)
        await self._link.send_audio(audio)
        await self._link.send_control(ServerMessageType.TTS_END)

    async def end_turn_without_speech(self) -> None:
        """Tura skończona, ale nie ma czego wypowiedzieć (sam tool call / samo rozumowanie).

        Satelita dostaje jawną ramkę `turn_end` i wraca do nasłuchu natychmiast. Wcześniej
        ten przypadek nie był obsłużony w ogóle — gateway po prostu kończył handler, a
        sesja zostawała w `PROCESSING` na zawsze."""
        logger.info(f"Tura bez treści do wypowiedzenia [sender_id: '{self.sender_id}'] — wracam do nasłuchu.")
        await self._link.send_control(ServerMessageType.TURN_END)
        await self.reset_to_listening()

    async def handle_playback_done(self) -> None:
        """Satelita potwierdziła koniec fizycznego odtwarzania — wracamy do nasłuchu."""
        if self.state != SessionState.SPEAKING:
            logger.warning(f"playback_done poza stanem SPEAKING [sender_id: '{self.sender_id}'] — zignorowano.")
        await self._set_state(SessionState.LISTENING_WAKEWORD)
        self._wakeword_detector.reset()

    async def reset_to_listening(self) -> None:
        """Awaryjny powrót do nasłuchu — wołane przez gateway, gdy tura kernela zakończyła
        się błędem/anulowaniem zanim `speak()` zostało wywołane (patrz `gateway.py`,
        `_on_error_or_cancelled`). Bez tego sesja utknęłaby w PROCESSING/SPEAKING na zawsze."""
        await self._set_state(SessionState.LISTENING_WAKEWORD)
        self._utterance_buffer.clear()
        self._wakeword_detector.reset()
