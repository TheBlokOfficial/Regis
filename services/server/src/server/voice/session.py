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

from shared import ServerMessageType, get_logger, peak_amplitude

from server.ports.stt import BaseSTTProvider
from server.ports.tts import BaseTTSProvider
from server.ports.wakeword import WakeWordDetector
from server.voice.events import VoiceEventType

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
        silence_amplitude_threshold: int = 0,
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
        self._silence_amplitude_threshold = silence_amplitude_threshold

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

    def handle_wake_stream_start(self) -> None:
        """Rozpoczyna niezależną porcję audio przepuszczoną przez bramkę satelity."""
        if self.state == SessionState.LISTENING_WAKEWORD:
            self._wakeword_detector.reset()

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

        # Nagranie, którego szczytowa amplituda nigdy nie przekroczyła progu — czyli to,
        # co sama satelita już uznaje za ciszę (ten sam próg co jej lokalny VAD) — trafiałoby
        # do Groq/Whisper jako czysta cisza/szum, na czym te modele halucynują pojedyncze
        # słowa ("Dzięki", "Okej") zamiast pustego tekstu. Czas trwania NIE jest tu sygnałem:
        # satelita zawsze czeka pełne `vad_silence_duration_ms` ciszy przed końcem nagrania
        # (patrz `desktop_satellite/vad.py::SilenceVadDetector`), więc nawet pusta wypowiedź
        # ma ten sam ~1.5s ogon co realna, krótka mowa.
        peak = peak_amplitude(audio)
        # Logowane zawsze (nie tylko przy odrzuceniu) — jedyny sposób, żeby dobrać/zweryfikować
        # `vad_amplitude_threshold` na realnym sprzęcie zamiast zgadywać z zewnątrz.
        logger.info(
            f"Amplituda nagrania [sender_id: '{self.sender_id}']: szczyt={peak}, "
            f"próg={self._silence_amplitude_threshold}, długość={len(audio)} bajtów."
        )
        if self._silence_amplitude_threshold > 0 and peak < self._silence_amplitude_threshold:
            logger.info(
                f"Nagranie zawiera wyłącznie ciszę/szum [sender_id: '{self.sender_id}'] "
                f"(szczytowa amplituda < {self._silence_amplitude_threshold}) — pomijam STT."
            )
            # `end_turn_without_speech()`, NIE `reset_to_listening()` bezpośrednio: satelita
            # (`desktop_satellite/session.py::handle_server_frame`) wraca do nasłuchu i wznawia
            # wysyłanie mikrofonu WYŁĄCZNIE po odebraniu `TURN_END`/`ERROR` — sam reset stanu
            # po stronie serwera (bez żadnej ramki do satelity) zostawiał ją uwięzioną w
            # `PROCESSING` na stałe, mimo że dashboard pokazywał już "Nasłuchiwanie".
            await self.end_turn_without_speech()
            return

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

        **Strumieniowo**: `tts_start` i pierwsza ramka audio lecą do satelity, gdy tylko
        dostawca zwróci PIERWSZY fragment — nie po zakończeniu całej syntezy. Wcześniej
        `synthesize()` czekało na komplet audio, mimo że i ElevenLabs (`convert()` zwraca
        `AsyncIterator[bytes]`), i protokół WS (`tts_start` -> N ramek -> `tts_end`), i
        odtwarzacz satelity od dawna umiały pracować strumieniowo — po prostu nic
        pomiędzy nimi z tego nie korzystało. Przy dłuższej odpowiedzi to różnica między
        "cisza przez kilka sekund" a dźwiękiem od razu po zakończeniu tury.

        `SYNTHESIZING` i `SPEAKING` to dwa różne stany, bo to dwa różne oczekiwania:
        pierwsze trwa tyle, ile zapytanie do dostawcy TTS DO PIERWSZEGO FRAGMENTU
        (dziś: pojedyncze żądanie HTTP, docelowo — pierwszy bajt strumienia), drugie
        tyle, ile realne odtwarzanie u klienta.

        Wyjątek dostawcy TTS **musi** być złapany tutaj: `speak()` jest wołane z handlera
        `EventBus`, a ten połyka wyjątki (`shared/event_bus.py::publish`), więc bez tego
        sesja zostawałaby w `SPEAKING`/`SYNTHESIZING` na zawsze, a satelita — z
        wstrzymanym mikrofonem. Wyjątek W TRAKCIE strumienia (część audio już poszła do
        satelity) jest traktowany inaczej niż przed pierwszym fragmentem: satelita ma już
        czym karmić głośnik, więc kończymy `tts_end` jak przy normalnym zakończeniu —
        `handle_playback_done()` i tak wróci do nasłuchu, gdy satelita doigra to, co
        dostała. Ucinanie w pół zdania jest gorsze od próby dokończenia, ale wciąż
        lepsze niż wieczne milczenie satelity czekającej na `tts_start`, który nigdy
        nie przyjdzie.
        """
        await self._set_state(SessionState.SYNTHESIZING)
        started = False
        try:
            async for chunk in self._tts_provider.synthesize_stream(text):
                if not chunk:
                    continue
                if not started:
                    started = True
                    await self._set_state(SessionState.SPEAKING)
                    await self._link.send_control(ServerMessageType.TTS_START)
                await self._link.send_audio(chunk)
        except Exception as err:
            # Sanityzacja jak wszędzie indziej: szczegół dostawcy tylko do logu.
            logger.error(f"Synteza mowy nie powiodła się [sender_id: '{self.sender_id}']: {err}")
            if not started:
                await self._link.send_error("Synteza mowy nieskonfigurowana lub niedostępna.")
                await self.reset_to_listening()
                return
            # Część audio już dotarła — kończymy strumień normalnie zamiast zostawiać
            # satelitę czekającą na ramki, których już nie będzie.

        if not started:
            logger.warning(f"Dostawca TTS zwrócił puste audio [sender_id: '{self.sender_id}'].")
            await self.end_turn_without_speech()
            return

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
        `_on_error_or_cancelled`). Bez tego sesja utknęłaby w PROCESSING/SPEAKING na zawsze.

        **Resetuje stan wyłącznie po stronie serwera.** Satelita
        (`desktop_satellite/session.py::handle_server_frame`) wraca do nasłuchu i wznawia
        wysyłanie mikrofonu wyłącznie po odebraniu `TURN_END`/`ERROR` — wołający musi wysłać
        jedną z tych ramek PRZED tym wywołaniem (patrz `end_turn_without_speech()`/
        `send_error()` u każdego istniejącego wywołującego), inaczej satelita utknie w
        `PROCESSING` na stałe, mimo że serwer już myśli, że wrócił do nasłuchu (żywy bug,
        naprawiony 2026-08-25: bramka ciszy w `handle_utterance_end()` wołała to bezpośrednio)."""
        await self._set_state(SessionState.LISTENING_WAKEWORD)
        self._utterance_buffer.clear()
        self._wakeword_detector.reset()
