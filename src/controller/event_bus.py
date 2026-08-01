"""
Szyna zdarzeń Kontrolera (EventBus).

Publikuje zdarzenia systemowe (rejestracje węzłów, satelit, decyzje routingowe,
tury konwersacji) do wszystkich aktywnych subskrybentów SSE.
Nowy klient przy połączeniu dostaje pełną historię ostatnich 500 eventów.
"""
import asyncio
import json
import logging
from collections import deque

_history: deque = deque(maxlen=500)
_subscribers: list[asyncio.Queue] = []


async def publish(event: dict) -> None:
    """Publikuje zdarzenie do historii i do wszystkich aktywnych subskrybentów."""
    _history.append(event)
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass
    logging.debug(f"[EventBus] Opublikowano: {event.get('type', '?')}")


async def subscribe() -> tuple[asyncio.Queue, list[dict]]:
    """Rejestruje nowego subskrybenta SSE.

    Zwraca: (kolejka z nowymi zdarzeniami, lista historycznych zdarzeń do odtworzenia)
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.append(q)
    return q, list(_history)


def unsubscribe(q: asyncio.Queue) -> None:
    """Wyrejestrowuje subskrybenta (np. gdy klient SSE rozłączy się)."""
    try:
        _subscribers.remove(q)
    except ValueError:
        pass
