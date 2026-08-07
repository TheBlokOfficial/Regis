"""
Wspólna logika kończenia tury konwersacji: zapis historii i publikacja do EventBus.

Używana przez oba pipeline (cloud i worker) — eliminuje duplikację kodu
która istniała w monolitycznym orchestrator.proxy_sse_to_queue().
"""
import datetime
import logging

import controller.core.session_store as session_store
import controller.core.event_bus as event_bus

# Maksymalna liczba tur przechowywanych w pamięci dla jednej sesji.
# Starsze tury są usuwane gdy historia przekroczy ten limit.
HISTORY_LIMIT = 10


async def save_and_publish(satellite_id: str, turn: dict) -> None:
    """
    Zapisuje turę konwersacji do sesji, trymuje historię i publikuje zdarzenie do EventBus.

    Args:
        satellite_id: Identyfikator sesji/satelity. Używany jako klucz w session_store.
        turn: Słownik tury konwersacji zawierający pola:
              user, assistant, tools, timestamp, room, elapsed_ms, profiler, model,
              worker_id, mode (opcjonalne).
    """
    session_store.append_to_session(satellite_id, turn)

    mode = turn.get("mode", "extended")
    if mode == "basic":
        # Tryb basic jest bezstanowy — czyścimy sesję po każdej turze
        session_store.clear_session_history(satellite_id)
    else:
        hist = session_store.get_session_history(satellite_id)
        if len(hist) > HISTORY_LIMIT:
            del hist[:-HISTORY_LIMIT]

    await event_bus.publish({
        "type": "conversation_turn",
        "user_text": turn.get("user", ""),
        "assistant_text": turn.get("assistant", ""),
        "worker_id": turn.get("worker_id", "unknown"),
        "satellite_id": satellite_id,
        "room": turn.get("room"),
        "tools": turn.get("tools", []),
        "tool_count": len(turn.get("tools", [])),
        "elapsed_ms": turn.get("elapsed_ms"),
        "profiler": turn.get("profiler", {}),
        "model": turn.get("model", "unknown"),
    })


def build_turn(
    user_message: str,
    assistant_response: str,
    satellite_id: str,
    room: str | None,
    worker_id: str,
    model_name: str,
    elapsed_ms: int,
    profiler: dict,
    tools: list[dict],
    mode: str = "extended",
) -> dict:
    """Buduje słownik tury konwersacji gotowy do zapisu i publikacji."""
    now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    return {
        "user": user_message,
        "assistant": assistant_response,
        "tools": tools,
        "timestamp": now,
        "satellite_id": satellite_id,
        "room": room,
        "elapsed_ms": elapsed_ms,
        "profiler": profiler,
        "model": model_name,
        "worker_id": worker_id,
        "mode": mode,
    }
