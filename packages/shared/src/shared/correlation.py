"""Identyfikator tury przenoszony przez cały asynchroniczny przebieg — bez
przekazywania go przez sygnatury.

**Po co.** Tura agenta przechodzi przez warstwy, które celowo o sobie nie wiedzą:
kernel (`server.agent`) prowadzi pętlę, `server.ai` rozstrzyga który backend LLM
odpowie, a obserwator (`server.telemetry`) zapisuje, co poleciało do modelu. Wszyscy
trzej potrzebują tej samej odpowiedzi na pytanie „której tury to dotyczy", ale
przeniesienie jej parametrem oznaczałoby rozszerzenie `BaseLLMProvider.generate_stream()`
o pole niemające nic wspólnego z generowaniem tekstu — czyli zabrudzenie portu
telemetrią i wymuszenie zmiany w każdej implementacji dostawcy.

**Dlaczego to działa.** Tura żyje w dokładnie jednym `asyncio.Task`
(`AgentEngine._spawn_turn`), a `ContextVar` propaguje się w dół takiego zadania
automatycznie — kto jest wołany w środku tury, ten widzi jej `TurnRef`, kto nie,
widzi `None`.

**Dlaczego w `shared`, a nie u obserwatora.** Ustawia to kernel, odczytuje
telemetria. Gdyby zmienna mieszkała w `server.telemetry`, `server.agent` musiałby ją
zaimportować — kernel zależałby od swojego obserwatora, dokładnie odwrotnie niż
powinien. `shared` jest warstwą przekrojową, którą importują już wszyscy
(`EventBus`, `get_logger`, `ConfigStore`), a korelacja jest bytem tej samej natury
co logowanie: infrastrukturą, nie domeną.
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True)
class TurnRef:
    """Tożsamość jednej tury agenta.

    Niezmienna: adres dostawy odpowiedzi potrafi się w trakcie tury zmienić
    (`TurnAddress.redirect_to`), ale to, *która to tura*, nigdy."""

    turn_id: str
    session_id: str
    sender_id: str | None = None
    started_at: float = field(default_factory=time.time)


def new_turn_id() -> str:
    """Losowy identyfikator tury — format mirrorujący `generate_session_id()`."""
    return f"turn_{uuid.uuid4().hex[:12]}"


_current_turn: ContextVar[TurnRef | None] = ContextVar("regis_current_turn", default=None)


def current_turn() -> TurnRef | None:
    """Tura, w której kontekście wykonuje się bieżący kod — albo `None`.

    `None` jest normalnym stanem, nie błędem: tak wygląda wywołanie spoza tury
    (skrypt, test, zapytanie REST o konfigurację)."""
    return _current_turn.get()


@contextmanager
def bind_turn(ref: TurnRef) -> Iterator[TurnRef]:
    """Wiąże `TurnRef` z bieżącym kontekstem na czas bloku."""
    token = _current_turn.set(ref)
    try:
        yield ref
    finally:
        _current_turn.reset(token)
