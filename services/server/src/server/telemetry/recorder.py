"""Przechwytywanie zrzutów wywołań LLM — dekorator na porcie, nie zmiana w kernelu.

**Dlaczego nie w `TurnRunner`.** Runner zna wiadomości, które sam zbudował, ale nie
wie, który dostawca obsłużył turę, ile kosztowała ani dlaczego model przestał pisać.
Doklejenie tego do kernela oznaczałoby wpuszczenie do niego wiedzy o dostawcach —
granicy, której `AGENTS.md` każe pilnować. Dekorator na `BaseLLMProvider` widzi
dokładnie jedno: `messages` i `tools` na wejściu, strumień zdarzeń na wyjściu. A że
dynamiczny system prompt i ulotny `turn_context` są już w `messages`, zrzut jest
kompletny bez pytania kogokolwiek o cokolwiek.

**Dlaczego kolektor prób jest osobnym bytem.** Sekwencja prób łańcucha fallbacku
jest widoczna wyłącznie *wewnątrz* `LLMRouter`, czyli pod dekoratorem. Router
potrzebuje obserwatora w konstruktorze, a dekorator potrzebuje routera — gdyby
obserwatorem była metoda dekoratora, konstrukcja byłaby cykliczna i wymagałaby
doklejania pola po fakcie. `TurnAttemptCollector` powstaje pierwszy i jest
przekazywany obu stronom, więc kompozycja w `main.py` zostaje jednokierunkowa.

**Dlaczego korelacja po `turn_id`, a nie przez `ContextVar` w dekoratorze.** Tura
to jedno zadanie asyncio, więc w danym momencie ma najwyżej jedno wywołanie LLM
w locie — słownik po `turn_id` rozstrzyga jednoznacznie. `ContextVar` ustawiany
wewnątrz generatora asynchronicznego miałby tu semantykę propagacji zależną od
tego, kto i jak steruje generatorem; to nie jest cecha, na której chce się opierać
księgowanie.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from shared import Event, EventBus, TurnRef, current_turn, get_logger

from server.ai.llm import LLMAttempt
from server.ai.llm.token_budget import estimate_tokens_from_chars
from server.events import ServerEventType
from server.ports.llm import (
    BaseLLMProvider,
    GenerationUsage,
    LLMMessage,
    ReasoningChunk,
    ToolCallRequest,
    ToolDefinition,
)
from server.telemetry.models import (
    AttemptSnapshot,
    GenerationRecord,
    GenerationStatus,
    MessageSnapshot,
    snapshot_messages,
    snapshot_tools,
)
from server.telemetry.store import GenerationLogStore

logger = get_logger("regis.telemetry.recorder")

_NO_TURN_KEY = "-"
"""Klucz dla wywołań spoza tury (skrypt, test, wywołanie headless). Współdzielony,
bo takie wywołania nie mają tożsamości — i nie mają jej po co mieć."""

_MAX_TRACKED_TURNS = 128
"""Sufit na słowniki księgowe. Tura zawsze kończy się jednym z trzech zdarzeń
(`done`/`error`/`cancelled`), więc wpisy sprzątają się same — sufit jest siatką
bezpieczeństwa na wypadek, gdyby kiedyś przestało to być prawdą."""


def _turn_key() -> str:
    turn = current_turn()
    return turn.turn_id if turn is not None else _NO_TURN_KEY


def _cap(bookkeeping: dict[str, Any]) -> None:
    """Usuwa najstarszy wpis, gdy słownik przekroczy sufit (dict trzyma kolejność wstawiania)."""
    while len(bookkeeping) > _MAX_TRACKED_TURNS:
        bookkeeping.pop(next(iter(bookkeeping)))


class TurnAttemptCollector:
    """Bufor prób łańcucha fallbacku, zbierany per tura."""

    def __init__(self) -> None:
        self._by_turn: dict[str, list[AttemptSnapshot]] = {}

    def record(self, attempt: LLMAttempt) -> None:
        """Wstrzykiwane do `LLMRouter` jako `attempt_observer`. Synchroniczne i tanie —
        router woła to w środku obsługi tury."""
        bucket = self._by_turn.setdefault(_turn_key(), [])
        bucket.append(
            AttemptSnapshot(
                instance_id=attempt.instance_id,
                instance_name=attempt.instance_name,
                provider_type=attempt.provider_type,
                model=attempt.model,
                position=attempt.position,
                outcome=attempt.outcome,
                error=attempt.error,
            )
        )
        _cap(self._by_turn)

    def drain(self) -> list[AttemptSnapshot]:
        """Zdejmuje próby bieżącej tury — wołane raz, po domknięciu wywołania."""
        return self._by_turn.pop(_turn_key(), [])

    def forget(self, turn_id: str) -> None:
        self._by_turn.pop(turn_id, None)


class RecordingLLMProvider(BaseLLMProvider):
    """`BaseLLMProvider`, który przepuszcza wszystko i zapisuje, co przepuścił.

    Poza dekorowaniem strumienia pełni jeszcze jedną rolę: wie, **czy tura w ogóle
    doszła do wywołania modelu**. Dzięki temu potrafi domknąć te przebiegi, po
    których nie zostaje żadne żądanie do zalogowania — awarię budowy kontekstu albo
    anulowanie w pierwszej sekundzie (patrz `handle_turn_end`)."""

    def __init__(
        self,
        inner: BaseLLMProvider,
        store: GenerationLogStore,
        attempts: TurnAttemptCollector,
    ) -> None:
        self._inner = inner
        self._store = store
        self._attempts = attempts
        self._turn_calls: dict[str, int] = {}

    # `AgentEngine.interact()` czyta `llm_provider.model` do `ChatResponseDTO`, a
    # `ContextBuilder` bywa strojony `max_tokens` — dekorator musi być pod tym
    # względem nieodróżnialny od dostawcy, którego opakowuje.
    @property
    def model(self) -> str:
        return self._inner.model

    @property
    def max_tokens(self) -> int | None:
        return self._inner.max_tokens

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | ReasoningChunk | ToolCallRequest | GenerationUsage]:
        turn = current_turn()
        key = _turn_key()
        call_index = self._turn_calls.get(key, 0)
        self._turn_calls[key] = call_index + 1
        _cap(self._turn_calls)

        # Zrzut robimy PRZED wywołaniem: `TurnRunner` dopisuje do tej samej listy
        # kolejne rundy pętli ReAct, więc po zakończeniu strumienia zobaczylibyśmy
        # już stan następnej rundy, nie tej.
        message_snapshot = snapshot_messages(messages)

        started = time.perf_counter()
        first_event_at: float | None = None
        answer_chars = 0
        tool_call_count = 0
        usage: GenerationUsage | None = None
        status: GenerationStatus = "ok"
        error: str | None = None

        try:
            async for event in self._inner.generate_stream(messages, tools=tools, **kwargs):
                if first_event_at is None:
                    first_event_at = time.perf_counter()
                if isinstance(event, GenerationUsage):
                    usage = event
                elif isinstance(event, ToolCallRequest):
                    tool_call_count += 1
                elif isinstance(event, str):
                    answer_chars += len(event)
                yield event
        except asyncio.CancelledError:
            status = "cancelled"
            raise
        except Exception as err:
            status = "error"
            # Surowo, bez sanityzacji: to jest panel diagnostyczny, a nie treść dla
            # użytkownika (tę `TurnRunner` zastępuje `USER_FACING_ERROR`).
            error = str(err)
            raise
        finally:
            self._store.submit(
                self._build_record(
                    turn=turn,
                    call_index=call_index,
                    messages=message_snapshot,
                    tools=tools,
                    started=started,
                    first_event_at=first_event_at,
                    answer_chars=answer_chars,
                    tool_call_count=tool_call_count,
                    usage=usage,
                    status=status,
                    error=error,
                )
            )

    # --------------------------------------------------------------------------

    def subscribe(self, event_bus: EventBus) -> None:
        """Podpina domykanie tur bez wywołania LLM. Trzy zdarzenia, bo dokładnie
        tyloma sposobami `TurnRunner` kończy turę."""
        for event_type in (ServerEventType.CHAT_DONE, ServerEventType.CHAT_ERROR, ServerEventType.CHAT_CANCELLED):
            event_bus.subscribe(event_type, self.handle_turn_end)

    async def handle_turn_end(self, event: Event[Any]) -> None:
        """Zamyka księgowanie tury i zapisuje wpis, jeśli nie doszło do żadnego wywołania.

        `EventBus.publish` awaituje handlery sekwencyjnie, w środku tury — ta metoda
        może więc wyłącznie odłożyć rekord do kolejki, nigdy dotknąć dysku."""
        turn = current_turn()
        if turn is None:
            return

        calls = self._turn_calls.pop(turn.turn_id, 0)
        attempts = self._attempts.drain()
        self._attempts.forget(turn.turn_id)
        if calls > 0:
            return

        payload = event.payload if isinstance(event.payload, dict) else {}
        self._store.submit(
            GenerationRecord(
                created_at=turn.started_at,
                session_id=turn.session_id,
                turn_id=turn.turn_id,
                sender_id=turn.sender_id,
                status="no_generation",
                # Treść z `EventBus` jest już sanityzowana dla użytkownika — pełny
                # szczegół tej klasy awarii (np. padnięty silnik świata przy budowie
                # kontekstu) leży w `data/logs/regis.log`.
                error=payload.get("error"),
                finish_reason=str(event.type),
                total_ms=(time.time() - turn.started_at) * 1000,
                attempts=attempts,
            )
        )

    def _build_record(
        self,
        *,
        turn: TurnRef | None,
        call_index: int,
        messages: list[MessageSnapshot],
        tools: list[ToolDefinition] | None,
        started: float,
        first_event_at: float | None,
        answer_chars: int,
        tool_call_count: int,
        usage: GenerationUsage | None,
        status: GenerationStatus,
        error: str | None,
    ) -> GenerationRecord:
        finished = time.perf_counter()
        attempts = self._attempts.drain()
        served = next((a for a in attempts if a.outcome == "ok"), None) or (attempts[-1] if attempts else None)

        real_usage = usage is not None and (
            usage.prompt_tokens is not None or usage.completion_tokens is not None
        )
        prompt_tokens = usage.prompt_tokens if usage is not None else None
        completion_tokens = usage.completion_tokens if usage is not None else None
        if not real_usage:
            # Estymata z tej samej heurystyki, którą bramkuje budżet TPM — jedna
            # definicja „ile to mniej więcej tokenów" w całym systemie.
            prompt_tokens = estimate_tokens_from_chars(sum(len(m.content) for m in messages))
            # Runda zakończona samym wywołaniem narzędzia nie wygenerowała ANI JEDNEGO
            # tokena odpowiedzi — zero, nie podłoga estymatora.
            completion_tokens = estimate_tokens_from_chars(answer_chars) if answer_chars else 0

        generation_seconds = finished - first_event_at if first_event_at is not None else None
        return GenerationRecord(
            created_at=turn.started_at if turn is not None else time.time(),
            session_id=turn.session_id if turn is not None else None,
            turn_id=turn.turn_id if turn is not None else None,
            call_index=call_index,
            sender_id=turn.sender_id if turn is not None else None,
            model=(usage.model if usage is not None and usage.model else None) or (served.model if served else None),
            provider_type=served.provider_type if served else None,
            instance_id=served.instance_id if served else None,
            instance_name=served.instance_name if served else None,
            status=status,
            finish_reason=usage.finish_reason if usage is not None else None,
            error=error,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=usage.cached_tokens if usage is not None else None,
            estimated=not real_usage,
            ttft_ms=(first_event_at - started) * 1000 if first_event_at is not None else None,
            total_ms=(finished - started) * 1000,
            output_tps=(
                completion_tokens / generation_seconds
                if completion_tokens and generation_seconds and generation_seconds > 0
                else None
            ),
            tool_calls=tool_call_count,
            messages=messages,
            tools=snapshot_tools(tools),
            attempts=attempts,
        )
