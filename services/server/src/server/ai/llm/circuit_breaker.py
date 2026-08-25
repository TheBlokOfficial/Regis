"""Lekki circuit breaker per instancja backendu LLM.

Gdy kandydat w łańcuchu fallbacku padnie z błędem PRZED wyemitowaniem
pierwszego zdarzenia strumienia (patrz `router.py` — to jedyny moment,
w którym zamiana na kolejnego kandydata jest bezpieczna), zostaje na chwilę
pominięty przy kolejnych turach zamiast być odpytywany ponownie od razu.
Czas odczekania: sparsowany z treści błędu, gdy dostawca go podaje (Groq
zwraca dosłownie "Please try again in 4.95s" przy HTTP 429), inaczej
domyślny cooldown.
"""

from __future__ import annotations

import re
import time

_RETRY_AFTER_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)

DEFAULT_COOLDOWN_SECONDS = 5.0


class CircuitBreaker:
    def __init__(self, default_cooldown_seconds: float = DEFAULT_COOLDOWN_SECONDS) -> None:
        self._default_cooldown = default_cooldown_seconds
        self._open_until: dict[str, float] = {}

    def is_open(self, instance_id: str) -> bool:
        until = self._open_until.get(instance_id)
        return until is not None and time.monotonic() < until

    def trip(self, instance_id: str, cooldown_seconds: float | None = None) -> None:
        self._open_until[instance_id] = time.monotonic() + (cooldown_seconds or self._default_cooldown)

    def trip_from_error(self, instance_id: str, error: Exception) -> None:
        """Wariant wołany z `except` — sam wyciąga sugerowany czas oczekiwania
        z treści błędu, jeśli dostawca go podał."""
        self.trip(instance_id, self._parse_retry_after(str(error)))

    @staticmethod
    def _parse_retry_after(message: str) -> float | None:
        match = _RETRY_AFTER_RE.search(message)
        if not match:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None
