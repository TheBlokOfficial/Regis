"""Zdarzenia tury: co kernel rozgłasza na `EventBus` i jak się na to zapisać.

Dwa powody, dla których to osobny moduł:

**1. Dwa identyfikatory, celowo rozdzielone.** Każde zdarzenie tury niesie:

* `session_id` — tożsamość sesji/pamięci. **Nigdy się nie zmienia** w trakcie tury;
  obserwatorzy sesji (`watch_session`, `interact_stream`, Web UI) filtrują po nim.
* `target_client_id` — adres dostawy. Startuje jako `sender_id` i może się zmienić
  w trakcie tury, gdy narzędzie zwróci `ToolResult.redirect_sender_id` (np.
  `WorldEngine.speak_in_room`); odbiorcy fizyczni (gniazdo satelity w `server.voice`)
  filtrują po nim. Kernel przestawia adres mechanicznie, nie znając powodu.

Wcześniej obie role pełniło jedno pole `session_id`, co działało wyłącznie dzięki
temu, że dla satelit `session_id == sender_id`. Dla klienta, u którego te wartości
się różnią (przeglądarka: sesja czatu vs `sender_id` z `localStorage`), przekierowanie
publikowało zdarzenia pod tagiem, którego nikt nie słuchał — **odpowiedź znikała bez
błędu**. `TurnAddress` trzyma tę parę jako jeden byt, żeby nie dało się jej rozdzielić
przez przypadek.

**2. Siedem prawie identycznych handlerów.** Subskrypcja zdarzeń sesji była siedmioma
domknięciami różniącymi się wyłącznie nazwą zdarzenia i kształtem payloadu. Dziś to
tabela — dodanie zdarzenia jest jednym wierszem, nie kolejnym domknięciem.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping

from shared import Event, EventBus

from server.events import ServerEventType

StreamEventType = Literal["user_message", "chunk", "tool_start", "tool_result", "done", "error", "cancelled"]


@dataclass
class StreamEvent:
    """Ustrukturyzowany element strumienia `interact_stream` — jeden do jednego
    z rodzajem zdarzenia `EventBus`, gotowy do serializacji SSE przez wywołującego."""

    type: StreamEventType
    payload: dict[str, Any]


@dataclass
class TurnAddress:
    """Para identyfikatorów tury. `session_id` jest niezmienny, `target_client_id`
    może przeskoczyć w trakcie tury na inny adres dostawy."""

    session_id: str
    target_client_id: str

    def redirect_to(self, client_id: str) -> None:
        self.target_client_id = client_id


class TurnEventPublisher:
    """Publikuje zdarzenia jednej tury, doklejając do każdego oba identyfikatory.

    Dzięki temu miejsce, które publikuje, nie musi pamiętać o adresowaniu — a adres
    da się przestawić w jednym miejscu (`address.redirect_to`), bez przekazywania
    zmiennej przez całą pętlę ReAct."""

    def __init__(self, event_bus: EventBus, address: TurnAddress) -> None:
        self._event_bus = event_bus
        self.address = address

    async def publish(self, event_type: ServerEventType, payload: Mapping[str, Any] | None = None) -> None:
        # `Mapping`, nie `dict` — wywołujący podaje też `ToolStepPayload` (TypedDict),
        # który nie jest przypisywalny do niezmiennego `dict[str, Any]`.
        await self._event_bus.publish(
            Event(
                type=event_type,
                payload={
                    "session_id": self.address.session_id,
                    "target_client_id": self.address.target_client_id,
                    **(payload or {}),
                },
                sender="agent_engine",
            )
        )


def _step_payload(event: Event[Any]) -> dict[str, Any]:
    # "type" wewnątrz ToolStepPayload ("tool_call"/"tool_result") jest tu zbędny —
    # StreamEvent.type ("tool_start"/"tool_result") już jednoznacznie opisuje rodzaj
    # zdarzenia SSE; zostawienie obu kolidowałoby przy spreadzie payloadu w routes/chat.py.
    return {k: v for k, v in event.payload.items() if k not in ("session_id", "type")}


def _chunk_payload(event: Event[Any]) -> dict[str, Any]:
    # `kind` ("answer"/"reasoning") przechodzi dalej nietknięty — to odbiorca decyduje,
    # co zrobić z rozumowaniem (Web UI pokazuje, TTS pomija).
    return {"chunk": event.payload.get("chunk", ""), "kind": event.payload.get("kind", "answer")}


_TRANSLATIONS: tuple[tuple[ServerEventType, StreamEventType, Callable[[Event[Any]], dict[str, Any]]], ...] = (
    (ServerEventType.CHAT_USER_MESSAGE, "user_message", lambda e: {"content": e.payload.get("content", "")}),
    (ServerEventType.CHAT_CHUNK, "chunk", _chunk_payload),
    (ServerEventType.TOOL_CALL_START, "tool_start", _step_payload),
    (ServerEventType.TOOL_CALL_RESULT, "tool_result", _step_payload),
    (ServerEventType.CHAT_DONE, "done", lambda e: {}),
    (ServerEventType.CHAT_ERROR, "error", lambda e: {"error": e.payload.get("error", "Nieznany błąd generowania.")}),
    (ServerEventType.CHAT_CANCELLED, "cancelled", lambda e: {}),
)
"""Zdarzenie `EventBus` -> element strumienia. Tabela, nie siedem domknięć."""


class SessionEventSubscription:
    """Subskrypcja zdarzeń JEDNEJ sesji, tłumacząca je na `StreamEvent` w kolejce.

    Używana przez `interact_stream()` (na czas jednej tury) i `watch_session()`
    (pasywnie, bez limitu czasu) — jedyna różnica jest w tym, kiedy wywołujący
    przestaje czytać, więc mechanizm jest wspólny.
    """

    def __init__(self, event_bus: EventBus, session_id: str) -> None:
        self._event_bus = event_bus
        self._session_id = session_id
        self.queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        self._handlers: list[tuple[ServerEventType, Any]] = []

    def __enter__(self) -> SessionEventSubscription:
        for event_type, stream_type, to_payload in _TRANSLATIONS:
            handler = self._make_handler(stream_type, to_payload)
            self._event_bus.subscribe(event_type, handler)
            self._handlers.append((event_type, handler))
        return self

    def __exit__(self, *_exc: object) -> None:
        for event_type, handler in self._handlers:
            self._event_bus.unsubscribe(event_type, handler)
        self._handlers.clear()

    def _make_handler(
        self, stream_type: StreamEventType, to_payload: Callable[[Event[Any]], dict[str, Any]]
    ) -> Callable[[Event[Any]], Any]:
        async def handler(event: Event[Any]) -> None:
            if event.payload.get("session_id") == self._session_id:
                await self.queue.put(StreamEvent(type=stream_type, payload=to_payload(event)))

        return handler
