"""Automat stanu jednej rozmowy głosowej.

```text
LISTENING_WAKEWORD -> (wake-word) -> RECORDING_UTTERANCE
    -> (utterance_end) -> PROCESSING (STT -> kernel -> TTS)
    -> SPEAKING -> (playback_done) -> LISTENING_WAKEWORD
```

Czysty automat treści/stanu — zero wiedzy o WebSocket czy EventBus. Doręczenie
(`SatelliteLink`) i odpalenie tury kernela (`on_transcript`) są wstrzykiwane,
żeby dało się testować bez prawdziwego gniazda ani prawdziwego `AgentEngine`
(patrz `gateway.py`, gdzie żyje realna implementacja `SatelliteLink`).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import Callable, Protocol

from shared import ServerMessageType, get_logger

from server.voice.stt import BaseSTTProvider
from server.voice.tts import BaseTTSProvider
from server.voice.wakeword import WakeWordDetector

logger = get_logger("regis.voice.session")


class SessionState(Enum):
    LISTENING_WAKEWORD = auto()
    RECORDING_UTTERANCE = auto()
    PROCESSING = auto()
    SPEAKING = auto()


class SatelliteLink(Protocol):
    """Minimalny kontrakt doręczenia do fizycznego połączenia — implementowany przez
    `VoiceConnection` (`gateway.py`)."""

    async def send_control(self, message_type: ServerMessageType) -> None: ...

    async def send_audio(self, chunk: bytes) -> None: ...


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
    ) -> None:
        self.sender_id = sender_id
        self.state = SessionState.LISTENING_WAKEWORD
        self._link = link
        self._wakeword_detector = wakeword_detector
        self._stt_provider = stt_provider
        self._tts_provider = tts_provider
        self._on_transcript = on_transcript
        self._utterance_buffer = bytearray()

    async def handle_audio_frame(self, chunk: bytes) -> None:
        """Ramka binarna PCM od satelity — znaczenie zależy od bieżącego stanu."""
        if self.state == SessionState.LISTENING_WAKEWORD:
            if self._wakeword_detector.process(chunk):
                logger.info(f"Wake-word wykryty [sender_id: '{self.sender_id}'].")
                self.state = SessionState.RECORDING_UTTERANCE
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
        self.state = SessionState.PROCESSING

        audio = bytes(self._utterance_buffer)
        self._utterance_buffer.clear()
        transcript = await self._stt_provider.transcribe(audio)
        logger.info(f"Transkrypcja [sender_id: '{self.sender_id}']: '{transcript}'")
        self._on_transcript(transcript)
        # Pozostajemy w PROCESSING — powrót do LISTENING_WAKEWORD następuje dopiero
        # po realnym odtworzeniu odpowiedzi (`speak()` -> `handle_playback_done()`),
        # sterowanym z zewnątrz przez gateway (odbiór CHAT_DONE z EventBus).

    async def speak(self, text: str) -> None:
        """Syntezuje i odtwarza odpowiedź — wołane przez gateway po odebraniu CHAT_DONE."""
        self.state = SessionState.SPEAKING
        audio = await self._tts_provider.synthesize(text)
        await self._link.send_control(ServerMessageType.TTS_START)
        await self._link.send_audio(audio)
        await self._link.send_control(ServerMessageType.TTS_END)

    async def handle_playback_done(self) -> None:
        """Satelita potwierdziła koniec fizycznego odtwarzania — wracamy do nasłuchu."""
        if self.state != SessionState.SPEAKING:
            logger.warning(f"playback_done poza stanem SPEAKING [sender_id: '{self.sender_id}'] — zignorowano.")
        self.state = SessionState.LISTENING_WAKEWORD
        self._wakeword_detector.reset()

    def reset_to_listening(self) -> None:
        """Awaryjny powrót do nasłuchu — wołane przez gateway, gdy tura kernela zakończyła
        się błędem/anulowaniem zanim `speak()` zostało wywołane (patrz `gateway.py`,
        `_on_error_or_cancelled`). Bez tego sesja utknęłaby w PROCESSING/SPEAKING na zawsze."""
        self.state = SessionState.LISTENING_WAKEWORD
        self._utterance_buffer.clear()
        self._wakeword_detector.reset()
