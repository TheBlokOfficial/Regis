"""
Agnostyczna Magistrala Wiadomości Regis (MessageBus — Warstwa 1 / Core).

Czysty, agnostyczny mechanizm posiadający wyłącznie 2 metody:
- subscribe(topic_or_type, subscriber)
- publish(message)
"""
import asyncio
from typing import Callable, Any


class MessageBus:
    """Agnostyczna magistrala wiadomości z metodami subscribe oraz publish."""

    def __init__(self):
        self._subscribers: dict[Any, list[Callable[..., Any]]] = {}
        self._execution_lock = asyncio.Lock()

    def subscribe(self, topic_or_type: Any, subscriber: Callable[..., Any]) -> None:
        """Rejestruje słuchacza dla konkretnego typu wiadomości lub tematu."""
        if topic_or_type not in self._subscribers:
            self._subscribers[topic_or_type] = []
        if subscriber not in self._subscribers[topic_or_type]:
            self._subscribers[topic_or_type].append(subscriber)

    async def publish(self, message: Any) -> Any:
        """Rozgłasza wiadomość do wszystkich zarejestrowanych słuchaczy."""
        msg_type = type(message) if not isinstance(message, str) else message
        subscribers = self._subscribers.get(msg_type, [])

        results = []
        async with self._execution_lock:
            for sub in subscribers:
                res = sub(message)
                if asyncio.iscoroutine(res):
                    results.append(await res)
                else:
                    results.append(res)

        if len(results) == 1 and hasattr(results[0], "__aiter__"):
            return results[0]
        return results


# Globalna instancja agnostycznej magistrali wiadomości Kontrolera
message_bus = MessageBus()


async def publish(message: Any) -> Any:
    """Pomocnicza funkcja modułowa do publikacji wiadomości."""
    return await message_bus.publish(message)
