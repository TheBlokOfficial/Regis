"""Kontrakt ramek WS między serwerem a satelitą.

Ramki binarne to zawsze surowe PCM16 mono (bez kodeka — najprostsze dla ESP32,
brak narzutu enkodowania/dekodowania), w obu kierunkach (mikrofon satelity ->
serwer, audio TTS serwer -> satelita). Ramki tekstowe to JSON control-plane,
symetryczny w obie strony — patrz `SatelliteMessageType`/`ServerMessageType`.

Dźwięki wake/stop-tone są lokalne (wypalone w firmware satelity/kliencie
desktopowym), nigdy strumieniowane z serwera — zero dodatkowego opóźnienia,
prostszy protokół.

Moduł żyje w `packages/shared`, nie w `services/server`, bo to kontrakt
współdzielony przez dwie niezależne usługi (`server` i `desktop_satellite`) —
tak jak DTO REST w `shared/contracts.py`.
"""

from __future__ import annotations

from enum import Enum

SAMPLE_RATE_HZ = 16000
SAMPLE_WIDTH_BYTES = 2  # PCM16
CHANNELS = 1


class SatelliteMessageType(str, Enum):
    """Wiadomości JSON wysyłane przez satelitę do serwera."""

    HELLO = "hello"
    """Pierwsza wiadomość po otwarciu połączenia: {"type": "hello", "capabilities": ["mic", "speaker"]}.
    Lista, nie sztywny enum — przyszły connector bez audio może zadeklarować mniej."""

    UTTERANCE_END = "utterance_end"
    """VAD satelity wykrył min. 1.5s ciszy po wake-wordzie — koniec wypowiedzi."""

    PLAYBACK_DONE = "playback_done"
    """Satelita skończyła fizyczne odtwarzanie audio TTS — serwer wraca do nasłuchu wake-wordu."""


class ServerMessageType(str, Enum):
    """Wiadomości JSON wysyłane przez serwer do satelity."""

    WAKE_DETECTED = "wake_detected"
    """Wake-word wykryty — satelita gra lokalny dźwięk potwierdzenia."""

    PLAY_STOP_TONE = "play_stop_tone"
    """Serwer potwierdza odebranie końca wypowiedzi — satelita gra lokalny dźwięk stopu."""

    TTS_START = "tts_start"
    """Zapowiedź: kolejne ramki binarne to audio odpowiedzi."""

    TTS_END = "tts_end"
    """Koniec strumienia audio odpowiedzi."""

    ERROR = "error"
    """Błąd protokołu/przetwarzania — payload niesie dodatkowo pole "detail"."""
