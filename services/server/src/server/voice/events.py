"""Typy zdarzeń domeny `voice` na współdzielonym `EventBus` (`agent_engine.event_bus`,
ten sam obiekt co `server.events.ServerEventType` dla czatu) — osobna przestrzeń nazw,
zero kolizji z `chat.*`. Zasilają dashboard "Klienci" w Web UI (`GET .../clients/watch`,
`voice_config.js`) — mirror architektury `AgentEngine.watch_session()` (czat): pasywna,
długożyjąca subskrypcja, zero trwałego zapisu po stronie serwera (czysto efemeryczne)."""

from enum import Enum


class VoiceEventType(str, Enum):
    SATELLITE_CONNECTED = "voice.satellite_connected"
    """Satelita (`sender_id`) zakończyła handshake — payload: `sender_id`."""

    SATELLITE_DISCONNECTED = "voice.satellite_disconnected"
    """Satelita się rozłączyła — payload: `sender_id`."""

    SATELLITE_STATE_CHANGED = "voice.satellite_state_changed"
    """Zmiana stanu automatu `VoiceSession` — payload: `sender_id`, `state`
    (nazwa `SessionState`, np. "LISTENING_WAKEWORD")."""

    SATELLITE_WAKE_WORD_DETECTED = "voice.satellite_wake_word_detected"
    """Wake-word wykryty — payload: `sender_id`, `score` (pewność detekcji, `None`
    dla `ThresholdEnergyWakeWordDetector`, który nie ma pojęcia ciągłego score)."""
