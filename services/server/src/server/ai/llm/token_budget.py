"""Lokalny, przybliżony budżet tokenów na minutę per instancja backendu LLM.

Optymalizacja, nie źródło prawdy: pozwala routerowi pominąć z góry preset,
o którym wiadomo, że jest bliski limitu TPM dostawcy (np. Groq: 8000 tok/min
na całą organizację), zamiast czekać na pełny round-trip zakończony HTTP 429.
Gdy estymacja się myli, `CircuitBreaker` (`circuit_breaker.py`) łapie realny
429 jako siatka bezpieczeństwa — te dwa mechanizmy się uzupełniają, żaden
z osobna nie musi być dokładny.

Licznik jest procesowy (nie przetrwa restartu) i celowo nietrwały na dysku —
to tylko podpowiedź, zerowanie przy restarcie jest nieszkodliwe (budżet po
prostu odbuduje się z realnego ruchu w ciągu pierwszej minuty).
"""

from __future__ import annotations

import time
from collections import deque

from server.ports.llm import LLMMessage

_CHARS_PER_TOKEN_ESTIMATE = 4
"""Zgrubna heurystyka (nie tokenizacja) — wystarczająca jako margines bezpieczeństwa
przy bramkowaniu, nie do rozliczeń.

Używana dziś w dwóch rolach, celowo rozdzielonych: **przed** wywołaniem, gdzie nic
innego nie istnieje (trzeba oszacować koszt tury, żeby zdecydować, czy w ogóle
próbować danego backendu), oraz **po** wywołaniu jako awaryjny zamiennik, gdy
dostawca nie zwróci `GenerationUsage` z realnymi licznikami (`router.py`)."""


def estimate_tokens_from_chars(char_count: int) -> int:
    """Prymityw estymacji — jedyne miejsce w systemie, które zna ten dzielnik."""
    return max(1, char_count // _CHARS_PER_TOKEN_ESTIMATE)


def estimate_tokens(messages: list[LLMMessage]) -> int:
    """Przybliżona liczba tokenów wejściowych — suma długości treści / 4."""
    return estimate_tokens_from_chars(sum(len(m.content) for m in messages))


class TokenBudgetTracker:
    """Okno kroczące zużycia tokenów, osobne per `instance_id`."""

    def __init__(self, window_seconds: float = 60.0) -> None:
        self._window_seconds = window_seconds
        self._usage: dict[str, deque[tuple[float, int]]] = {}

    def record(self, instance_id: str, tokens: int) -> None:
        """Odnotowuje zużycie po udanym wywołaniu (wejście + wyjście).

        Realne liczniki z `GenerationUsage`, gdy dostawca je podał; estymata z
        `estimate_tokens()` w przeciwnym razie — decyduje `router.py`."""
        self._prune(instance_id)
        self._usage.setdefault(instance_id, deque()).append((time.monotonic(), tokens))

    def used_tokens(self, instance_id: str) -> int:
        self._prune(instance_id)
        return sum(tokens for _, tokens in self._usage.get(instance_id, ()))

    def has_budget(self, instance_id: str, estimated_tokens: int, limit: int) -> bool:
        """`limit` pochodzi od wołającego (np. `options["tpm_limit"]` presetu) —
        tracker nie zna z góry limitów konkretnych dostawców."""
        return self.used_tokens(instance_id) + estimated_tokens <= limit

    def _prune(self, instance_id: str) -> None:
        window = self._usage.get(instance_id)
        if not window:
            return
        cutoff = time.monotonic() - self._window_seconds
        while window and window[0][0] < cutoff:
            window.popleft()
