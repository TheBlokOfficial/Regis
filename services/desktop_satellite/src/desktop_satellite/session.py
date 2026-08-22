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

from shared import SatelliteMessageType, ServerMessageType, get_logger

from desktop_satellite.audio import MicCapture, SpeakerPlayback, synth_tone
from desktop_satellite.protocol_client import SatelliteLink, ServerFrame, parse_server_message_type
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
        self._response_buffer = bytearray()

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

        if isinstance(frame, dict) and parse_server_message_type(frame) == ServerMessageType.CLIENT_CONFIG:
            silence_ms = float(frame["silence_duration_ms"])
            amplitude = int(frame["amplitude_threshold"])
            logger.info(f"Konfiguracja VAD z serwera: cisza={silence_ms:.0f}ms, próg amplitudy={amplitude}.")
            return self._vad_factory(silence_ms, amplitude)

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

    async def handle_server_frame(self, frame: ServerFrame) -> None:
        if isinstance(frame, (bytes, bytearray)):
            if self.state == SessionState.SPEAKING:
                self._response_buffer.extend(frame)
            return

        message_type = parse_server_message_type(frame)
        if message_type == ServerMessageType.WAKE_DETECTED:
            await self._on_wake_detected()
        elif message_type == ServerMessageType.PLAY_STOP_TONE:
            await self._speaker.play_cue(STOP_SOUND_NAME, synth_tone(STOP_TONE_HZ, TONE_DURATION_MS))
        elif message_type == ServerMessageType.TTS_START:
            self.state = SessionState.SPEAKING
            self._response_buffer.clear()
        elif message_type == ServerMessageType.TTS_END:
            await self._on_tts_end()
        elif message_type == ServerMessageType.ERROR:
            logger.warning(f"Błąd zgłoszony przez serwer: {frame.get('detail')}")
            self._reset_to_listening()
        else:
            logger.warning(f"Nieznany typ wiadomości od serwera: {frame.get('type')!r}.")

    async def _on_wake_detected(self) -> None:
        assert self._vad is not None, "SatelliteSession.run() nie zostało wywołane."
        logger.info("Wake-word wykryty.")
        self.state = SessionState.RECORDING_UTTERANCE
        self._vad.reset()
        await self._speaker.play_cue(WAKE_SOUND_NAME, synth_tone(WAKE_TONE_HZ, TONE_DURATION_MS))

    async def _on_tts_end(self) -> None:
        audio = bytes(self._response_buffer)
        self._response_buffer.clear()
        await self._speaker.play(audio)
        await self._link.send_control(SatelliteMessageType.PLAYBACK_DONE)
        self._reset_to_listening()

    def _reset_to_listening(self) -> None:
        assert self._vad is not None, "SatelliteSession.run() nie zostało wywołane."
        self.state = SessionState.LISTENING_WAKEWORD
        self._response_buffer.clear()
        self._vad.reset()
