"""Generyczny kontrakt granicy Gateway <-> Dostawca kontekstu (wizja, sekcja 2).

Dostawca kontekstu jest kategorią równoległą do Pluginu — nie dostarcza
narzędzi ani encji, tylko płaskie fakty o świecie i o pochodzeniu requestu.
Zawsze domenowo pusty (nigdy nie ujawnia, że np. plugin Smart Home istnieje).
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Fact:
    """Pojedynczy, płaski fakt kontekstowy (klucz-wartość)."""

    key: str
    value: str


class ContextProvider(Protocol):
    """Cokolwiek dostarczające agentowi fakty niezwiązane z żadnym narzędziem."""

    async def get_facts(self) -> list[Fact]:
        """Zwraca fakty tego dostawcy na czas jednej interakcji agenta."""
        ...
