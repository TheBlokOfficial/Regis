"""Generyczny kontrakt granicy Gateway <-> Plugin (Warstwa 1).

Gateway zna wyłącznie ten protokół — nigdy konkretnego pluginu (np. Smart
Home). Plugin nie musi nawet importować tego modułu, wystarczy że
strukturalnie pasuje kształtem (typing.Protocol — strukturalne typowanie).

Kontrakt jest czystą deklaracją kształtu (czasownika — parametry narzędzia,
i rzeczownika — pola encji), zero logiki i zero stanu — nigdy nie istnieje
jako uruchomiony obiekt (wizja, sekcja 2, "Kontrakt").
"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from server.agent.backend import ToolDefinition, ToolResult

ToolDispatch = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True)
class Fact:
    """Pojedynczy, płaski fakt kontekstowy (klucz-wartość).

    Kontekst do zrozumienia, nigdy do adresowania — zawsze z bliźniaczym
    narzędziem dostarczającym tę samą treść na żądanie (wizja, sekcja 4.5).
    """

    key: str
    value: str


@dataclass(frozen=True)
class EntityCapability:
    """Etykieta możliwości encji w obrębie jednego narzędzia.

    :param tool_name: Nazwa narzędzia, które ta encja obsługuje.
    :param features: Granularne cechy wspierane w obrębie tego narzędzia
        (np. dla hipotetycznego 'set_light': {'brightness'} bez 'rgb').
        Pusty zbiór oznacza pełne, niepodzielone wsparcie narzędzia —
        dzisiejszy przypadek dla wszystkich encji Smart Home.
    """

    tool_name: str
    features: frozenset[str] = frozenset()


@dataclass
class EntitySpec:
    """Generyczny kształt "rzeczownika" — pojedyncza rzecz do interakcji.

    Konkretna realizacja (np. `Device` ze Smart Home) jest pojęciem
    konkretnego pluginu, nie kernela (wizja, sekcja 5) — ten typ opisuje
    wyłącznie wspólny kształt, jaki każdy plugin musi wypełnić.

    :param id: Gdy zwracane przez Plugin do Gateway — wewnętrzne, nieopaque
        odniesienie znane tylko temu pluginowi. Gdy przekazywane dalej do
        kernela — opaque identyfikator nadany przez Gateway (patrz `gateway.py`).
    :param name: Przyjazna nazwa widoczna dla agenta/użytkownika.
    :param capabilities: Zbiór etykiet możliwości (patrz `EntityCapability`).
    """

    id: str
    name: str
    capabilities: frozenset[EntityCapability]


@dataclass
class PluginContribution:
    """Pełny wkład jednego pluginu na czas jednej interakcji agenta."""

    tools: list[ToolDefinition]
    entities: list[EntitySpec]
    dispatch: ToolDispatch
    facts: list[Fact] = field(default_factory=list)
    """Fakty — opcjonalny wkład na równi z narzędziami i encjami (wizja,
    sekcja 2 i 4.5). Każdy Fakt tu zwrócony musi mieć bliźniacze narzędzie
    dostarczające tę samą treść na żądanie."""


class PluginProvider(Protocol):
    """Jedyna jednostka, z którą rozmawia Gateway (wizja, sekcja 2)."""

    plugin_id: str
    """Stabilna tożsamość pluginu — wejście do wyliczania opaque ID encji
    (musi być stała między turami i uruchomieniami procesu)."""

    async def build(self, facts: list[Fact]) -> PluginContribution:
        """Buduje pełny, spłaszczony wkład pluginu (narzędzia + encje, z już
        rozwiązanymi grupami) na czas jednej interakcji agenta.

        :param facts: Fakty zebrane przez Gateway w tej turze od pluginów
            zbudowanych wcześniej, w kolejności rejestracji — plugin może
            (opcjonalnie) użyć ich do decyzji co pokazać jako priorytet,
            budując swoje encje.
        """
        ...
