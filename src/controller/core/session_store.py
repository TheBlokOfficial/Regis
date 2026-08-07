"""
Zarządzanie historią aktywnych sesji konwersacji w pamięci Kontrolera.

Każda sesja jest identyfikowana przez satellite_id (lub "default" dla Web UI).
Sesje są automatycznie wygaszane przez heartbeat po 60s bezczynności.
"""
import time

# Słownik aktywnych sesji: {satellite_id: [{"user": ..., "assistant": ..., ...}]}
conversation_sessions: dict[str, list[dict]] = {}

# Czas ostatniej interakcji dla każdej sesji — używany przez heartbeat do wygaszania
session_last_interaction_times: dict[str, float] = {}


def get_session_history(satellite_id: str | None = None) -> list[dict]:
    """Pobiera historię konwersacji dla określonej Satelity / sesji."""
    sid = satellite_id or "default"
    return conversation_sessions.get(sid, [])


def append_to_session(satellite_id: str | None, turn: dict) -> None:
    """Dodaje turę konwersacji do sesji i aktualizuje czas ostatniej interakcji."""
    sid = satellite_id or "default"
    if sid not in conversation_sessions:
        conversation_sessions[sid] = []
    conversation_sessions[sid].append(turn)
    session_last_interaction_times[sid] = time.time()


def clear_session_history(satellite_id: str | None = None) -> None:
    """Czyści pamięć konkretnej sesji lub wszystkich sesji (gdy satellite_id jest None)."""
    if satellite_id:
        conversation_sessions.pop(satellite_id, None)
        session_last_interaction_times.pop(satellite_id, None)
    else:
        conversation_sessions.clear()
        session_last_interaction_times.clear()
