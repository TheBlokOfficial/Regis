"""
Wspólna logika kończenia tury konwersacji: zapis historii i publikacja do EventBus.
"""
import datetime
import logging
import requests
import asyncio

import controller.core.client_registry as client_registry
import controller.agent.session.store as session_store
from controller.core.message_bus import message_bus
from controller.messages import ConversationTurnMessage, ClearHistoryMessage



logger = logging.getLogger(__name__)

# Maksymalna liczba tur przechowywanych w pamięci dla jednej sesji.
# Starsze tury są usuwane gdy historia przekroczy ten limit.
HISTORY_LIMIT = 10


async def save_and_publish(satellite_id: str, turn: dict) -> None:
    """
    Zapisuje turę konwersacji do sesji, trymuje historię i publikuje zdarzenie do MessageBus.

    Args:
        satellite_id: Identyfikator sesji/satelity. Używany jako klucz w session_store.
        turn: Słownik tury konwersacji zawierający pola:
              user, assistant, tools, timestamp, room, elapsed_ms, profiler, model,
              worker_id.
    """
    session_store.append_to_session(satellite_id, turn)

    hist = session_store.get_session_history(satellite_id)
    if len(hist) > HISTORY_LIMIT:
        del hist[:-HISTORY_LIMIT]

    msg = ConversationTurnMessage(
        satellite_id=satellite_id,
        user_text=turn.get("user", ""),
        assistant_text=turn.get("assistant", ""),
        worker_id=turn.get("worker_id", "unknown"),
        room=turn.get("room"),
        tools=turn.get("tools", []),
        elapsed_ms=turn.get("elapsed_ms"),
        profiler=turn.get("profiler", {}),
        model=turn.get("model", "unknown"),
    )
    await message_bus.publish(msg)



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
    }


async def _on_clear_history(msg: ClearHistoryMessage) -> None:
    """Resetuje historię konwersacji w pamięci Kontrolera oraz powiązanych węzłach/usługach."""
    session_store.clear_session_history(msg.satellite_id)

    def _notify_worker(worker_url: str):
        try:
            requests.post(f"{worker_url}/v1/clear_history", timeout=2)
        except Exception as e:
            logger.debug(f"Nie udało się powiadomić usługi LLM o czyszczeniu historii: {e}")

    for worker in client_registry.get_llm_clients():
        await asyncio.to_thread(_notify_worker, worker['base_url'])

message_bus.subscribe(ClearHistoryMessage, _on_clear_history)
