"""Automat stanu jednej sesji satelity desktopowej — klienckie odbicie `VoiceSession`
(`server/voice/session.py`):

```text
LISTENING_WAKEWORD -> (wake_detected) -> RECORDING_UTTERANCE
    -> (lokalny VAD: cisza) -> PROCESSING (wysyła utterance_end, czeka na odpowiedź)
    -> (tts_start..tts_end) -> SPEAKING -> (playback_done) -> LISTENING_WAKEWORD
```

Czysty automat + wstrzyknięte zależności (`link`/`speaker`/`vad`) — testowalny
bez prawdziwego gniazda WS ani prawdziwego mikrofonu/głośnika, tym samym
wzorcem co po stronie serwera.
"""

from __future__ import annotations

import asyncio
from enum import Enum, auto
from typing import Callable

from shared import (
    ClientConfigFrame,
    ErrorFrame,
    PlayStopToneFrame,
    SatelliteMessageType,
    TtsEndFrame,
    TtsStartFrame,
    TurnEndFrame,
    WakeDetectedFrame,
    get_logger,
)

from desktop_satellite.audio import MicCapture, SpeakerPlayback, synth_tone
from desktop_satellite.protocol_client import IncomingFrame, SatelliteLink
from desktop_satellite.vad import SilenceVadDetector

logger = get_logger("regis.desktop_satellite.session")

VadFactory = Callable[[float, int], SilenceVadDetector]

# Ile czasu satelita czeka na CLIENT_CONFIG zaraz po handshake, zanim uzna, że serwer
# go nie wyśle (starsza wersja protokołu) i spadnie na lokalne defaulty `vad_factory`.
CLIENT_CONFIG_TIMEOUT_SECONDS = 3.0

# Dźwięki systemowe Windows Speech Recognition (`C:\Windows\Media\*.wav`) — te same
# dźwięki, które kiedyś towarzyszyły Cortanie. `SpeakerPlayback.play_cue` odtwarza je
# preferencyjnie, z fallbackiem do syntezowanego tonu (Linux / plik nieobecny).
WAKE_SOUND_NAME = "Speech On"
STOP_SOUND_NAME = "Speech Sleep"
WAKE_TONE_HZ = 880.0
STOP_TONE_HZ = 440.0
TONE_DURATION_MS = 150.0


class SessionState(Enum):
    LISTENING_WAKEWORD = auto()
    RECORDING_UTTERANCE = auto()
    PROCESSING = auto()
    SPEAKING = auto()


class SatelliteSession:
    """Jedna sesja rozmowy z serwerem — jedna instancja per połączenie WS.

    VAD wykonuje się lokalnie (zero rundtripu na decyzję "koniec wypowiedzi"), ale
    jego próg jest centralnie skonfigurowany na serwerze — `vad_factory` buduje
    konkretny `SilenceVadDetector` dopiero w `run()`, po otrzymaniu `CLIENT_CONFIG`
    (patrz `_await_client_config`), zamiast dostawać gotową instancję z góry."""

    def __init__(self, link: SatelliteLink, speaker: SpeakerPlayback, vad_factory: VadFactory) -> None:
        self.state = SessionState.LISTENING_WAKEWORD
        self._link = link
        self._speaker = speaker
        self._vad_factory = vad_factory
        self._vad: SilenceVadDetector | None = None

    async def run(self, mic: MicCapture) -> None:
        """Wysyła handshake, czeka na `CLIENT_CONFIG` serwera (parametry VAD), po czym
        pompuje ramki mikrofonu/serwera równolegle, dopóki jedna ze stron nie padnie
        (`TaskGroup` anuluje drugą pętlę przy błędzie)."""
        await self._link.send_hello(["mic", "speaker"])
        logger.info("Handshake wysłany, czekam na konfigurację serwera...")
        self._vad = await self._await_client_config()
        logger.info("Satelita nasłuchuje.")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._pump_mic(mic))
            tg.create_task(self._pump_server())

    async def _await_client_config(self) -> SilenceVadDetector:
        """Czeka `CLIENT_CONFIG_TIMEOUT_SECONDS` na ramkę `client_config` z parametrami
        VAD. Brak odpowiedzi (starszy serwer) albo nieoczekiwana ramka -> log ostrzeżenia
        i lokalne defaulty `vad_factory` (łagodna degradacja, ten sam wzorzec co reszta
        projektu przy braku configu)."""
        try:
            frame = await asyncio.wait_for(self._link.recv(), timeout=CLIENT_CONFIG_TIMEOUT_SECONDS)
        except TimeoutError:
            logger.warning("Serwer nie przysłał CLIENT_CONFIG w czasie — używam lokalnych defaultów VAD.")
            return self._vad_factory_defaults()

        if isinstance(frame, ClientConfigFrame):
            logger.info(
                f"Konfiguracja VAD z serwera: cisza={frame.silence_duration_ms:.0f}ms, "
                f"próg amplitudy={frame.amplitude_threshold}."
            )
            return self._vad_factory(frame.silence_duration_ms, frame.amplitude_threshold)

        logger.warning(f"Oczekiwano CLIENT_CONFIG, dostano: {frame!r} — używam lokalnych defaultów VAD.")
        return self._vad_factory_defaults()

    def _vad_factory_defaults(self) -> SilenceVadDetector:
        return self._vad_factory(1500.0, 500)

    async def _pump_mic(self, mic: MicCapture) -> None:
        while True:
            chunk = await mic.frames()
            await self.handle_mic_frame(chunk)

    async def _pump_server(self) -> None:
        while True:
            frame = await self._link.recv()
            await self.handle_server_frame(frame)

    # --------------------------------------------------------------------------
    # Logika automatu — testowalna bez gniazda/sprzętu
    # --------------------------------------------------------------------------

    async def handle_mic_frame(self, chunk: bytes) -> None:
        if self.state == SessionState.LISTENING_WAKEWORD:
            await self._link.send_audio(chunk)
            return
        if self.state == SessionState.RECORDING_UTTERANCE:
            assert self._vad is not None, "SatelliteSession.run() nie zostało wywołane."
            await self._link.send_audio(chunk)
            if self._vad.process(chunk):
                logger.info("Lokalny VAD: cisza wykryta — koniec wypowiedzi.")
                self.state = SessionState.PROCESSING
                await self._link.send_control(SatelliteMessageType.UTTERANCE_END)
            return
        # PROCESSING/SPEAKING: nie strumieniujemy mikrofonu — uniknięcie nagrywania
        # własnego odtwarzania bez echo-cancellation (ten sam powód co server-side).

    async def handle_server_frame(self, frame: IncomingFrame) -> None:
        if isinstance(frame, (bytes, bytearray)):
            if self.state == SessionState.SPEAKING:
                # Fragment leci PROSTO na otwarty strumień (patrz `TTS_START` niżej) —
                # gra w miarę nadejścia, bez czekania na komplet odpowiedzi.
                await self._speaker.write_chunk(bytes(frame))
            return

        if isinstance(frame, WakeDetectedFrame):
            await self._on_wake_detected()
        elif isinstance(frame, PlayStopToneFrame):
            await self._speaker.play_cue(STOP_SOUND_NAME, synth_tone(STOP_TONE_HZ, TONE_DURATION_MS))
        elif isinstance(frame, TtsStartFrame):
            self.state = SessionState.SPEAKING
            await self._speaker.start_stream()
        elif isinstance(frame, TtsEndFrame):
            await self._on_tts_end()
        elif isinstance(frame, TurnEndFrame):
            # Tura skończona, ale nie ma czego odtworzyć (np. model wykonał samo wywołanie
            # narzędzia). Bez dźwięku — wracamy do nasłuchu, tak jakby nic nie zaszło.
            logger.info("Tura zakończona bez odpowiedzi głosowej — wracam do nasłuchu.")
            self._reset_to_listening()
        elif isinstance(frame, ErrorFrame):
            logger.warning(f"Błąd zgłoszony przez serwer: {frame.detail}")
            self._reset_to_listening()
        else:
            # `None` = ramka nierozpoznana; kodek zalogował już jej treść. Ignorujemy,
            # zamiast zrywać połączenie — nowszy serwer może mówić więcej niż my znamy.
            logger.debug("Pominięto nierozpoznaną ramkę serwera.")

    async def _on_wake_detected(self) -> None:
        assert self._vad is not None, "SatelliteSession.run() nie zostało wywołane."
        logger.info("Wake-word wykryty.")
        self.state = SessionState.RECORDING_UTTERANCE
        self._vad.reset()
        await self._speaker.play_cue(WAKE_SOUND_NAME, synth_tone(WAKE_TONE_HZ, TONE_DURATION_MS))

    async def _on_tts_end(self) -> None:
        # `stop_stream()` czeka, aż wszystko, co już przyjęte, dogra się do końca —
        # dopiero POTEM `playback_done` jest prawdą, nie tylko sygnałem "odebrałem dane".
        await self._speaker.stop_stream()
        await self._link.send_control(SatelliteMessageType.PLAYBACK_DONE)
        self._reset_to_listening()

    def _reset_to_listening(self) -> None:
        assert self._vad is not None, "SatelliteSession.run() nie zostało wywołane."
        self.state = SessionState.LISTENING_WAKEWORD
        self._vad.reset()
