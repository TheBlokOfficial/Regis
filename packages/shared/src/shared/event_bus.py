import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Generic, List, TypeVar

from shared.logging import get_logger

logger = get_logger("regis.shared.events")

# Generyczny parametr typu dla ładunku wiadomości/zdarzenia (Payload)
T = TypeVar("T")

# Typ reprezentujący asynchroniczną funkcję obsługi zdarzenia
EventHandler = Callable[["Event[Any]"], Awaitable[None]]


@dataclass
class Event(Generic[T]):
    """Generyczna, silnie typowana koperta wiadomości/zdarzenia.

    Parametr typu T określa strukturę i typ ładunku (payload).
    """

    type: str
    payload: T
    sender: str = "system"
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Asynchroniczna, silnie typowana magistrala komunikatów (In-Memory Pub/Sub Message Bus)."""

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: Callable[[Event[Any]], Awaitable[None]]) -> None:
        """Rejestruje funkcję obsługi dla danego typu zdarzenia (lub '*' dla wszystkich)."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []

        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug(f"Zarejestrowano słuchacza dla zdarzenia '{event_type}'")

    def unsubscribe(self, event_type: str, handler: Callable[[Event[Any]], Awaitable[None]]) -> None:
        """Wyrejestrowuje słuchacza dla danego typu zdarzenia."""
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
            logger.debug(f"Wyrejestrowano słuchacza dla zdarzenia '{event_type}'")

    async def publish(self, event: Event[Any]) -> None:
        """Rozgłasza silnie typowaną wiadomość asynchronicznie do zarejestrowanych subskrybentów."""
        logger.debug(f"Publikowanie zdarzenia [{event.type}] od {event.sender}")

        handlers: List[EventHandler] = list(self._subscribers.get(event.type, []))
        wildcard_handlers: List[EventHandler] = list(self._subscribers.get("*", []))
        all_handlers = handlers + wildcard_handlers

        if not all_handlers:
            return

        for handler in all_handlers:
            try:
                res = handler(event)
                if asyncio.iscoroutine(res):
                    await res
            except Exception as e:
                logger.error(
                    f"Błąd podczas obsługi zdarzenia [{event.type}] przez {handler.__name__}: {e}",
                    exc_info=True,
                )
