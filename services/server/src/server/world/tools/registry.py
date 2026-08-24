"""Zestaw narzędzi udostępnionych agentowi w jednej turze.

Wcześniej definicje narzędzi były literałami **w środku** `WorldEngine.build()`,
a rozgałęzienie „które narzędzie wołać" — łańcuchem `if name == ...` w domknięciu
tuż pod nimi. Dodanie jednego narzędzia wymagało operacji w środku funkcji
budującej prompt, czyli w miejscu, które z narzędziami nie ma nic wspólnego.

Dziś narzędzie to para **definicja + handler** (`Tool`), a `ToolSet` składa je
w to, czego oczekuje kernel: listę definicji i jedną funkcję `dispatch`.

To **nie jest** powrót do generycznej wielorozszerzeniowości, którą projekt
świadomie porzucił (`docs/manifest.md`, sekcja 5). Nie ma tu protokołu między
niezależnymi rozszerzeniami, rejestracji typów ani przełącznika enable/disable —
to zwykły słownik nazwa → funkcja wewnątrz jednego, konkretnego silnika świata.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from shared import get_logger

from server.ports.llm import ToolDefinition, ToolResult
from server.world.tools.home_assistant import HomeAssistantToolExecutor

logger = get_logger("regis.world.tools")

ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True)
class Tool:
    """Narzędzie agenta: co model o nim wie (`definition`) i co się dzieje po wywołaniu."""

    definition: ToolDefinition
    handler: ToolHandler


class ToolSet:
    """Narzędzia jednej tury — definicje dla modelu + routing wywołań.

    Urządzenia Home Assistant obsługiwane są przez `executor`, a nie przez wpisy
    w słowniku: ich nazwy (`get_state`/`turn_on`/`turn_off`) są stałe, a routing
    po `entity_id` (urządzenie/grupa/tablica) jest już zamknięty wewnątrz
    egzekutora. Wpisywanie ich pojedynczo dublowałoby tamtą logikę.
    """

    def __init__(self, tools: list[Tool], ha_executor: HomeAssistantToolExecutor | None = None) -> None:
        self._tools = {tool.definition.name: tool for tool in tools}
        self._ha_executor = ha_executor
        self._ha_definitions: list[ToolDefinition] = []
        self._ha_tool_names: frozenset[str] = frozenset()

    def add_home_assistant(self, executor: HomeAssistantToolExecutor | None, definitions: list[ToolDefinition]) -> None:
        """Dokłada narzędzia urządzeń. `executor is None` przy skonfigurowanych definicjach
        oznacza „agent widzi urządzenia, ale nie ma czym ich dotknąć" — stan przejściowy
        (klient HA nie powstał), w którym wywołanie zwróci błąd zamiast wyjątku."""
        self._ha_executor = executor
        self._ha_definitions = definitions
        self._ha_tool_names = frozenset(d.name for d in definitions)

    @property
    def definitions(self) -> list[ToolDefinition]:
        """Kolejność: najpierw narzędzia wbudowane Świata, potem urządzenia — dokładnie
        tak, jak widział je model przed wydzieleniem tego modułu."""
        return [tool.definition for tool in self._tools.values()] + list(self._ha_definitions)

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Jedyne wejście wywołań narzędzi z pętli ReAct kernela.

        Wyjątek egzekutora HA jest zamieniany na `ToolResult(is_error=True)`, nie
        propagowany: pętla agentyczna ma dostać wynik, z którym model może coś zrobić,
        a nie wywrócić całą turę przez timeout jednej żarówki.

        Do egzekutora trafiają **wyłącznie nazwy, które faktycznie zadeklarowaliśmy**.
        Wcześniej dostawał wszystko, czego nie znalazł słownik — więc halucynowana
        nazwa narzędzia wracała do modelu jako "Nie znaleziono żadnej pasującej encji",
        czyli komunikat kierujący go na poprawianie `entity_id` zamiast na to, że
        takiego narzędzia po prostu nie ma.
        """
        tool = self._tools.get(name)
        if tool is not None:
            return await tool.handler(arguments)
        if name in self._ha_tool_names:
            if self._ha_executor is None:
                return ToolResult(
                    is_error=True,
                    content=f"Narzędzie '{name}' jest chwilowo niedostępne (brak połączenia z Home Assistant).",
                )
            try:
                return await self._ha_executor.execute(name, arguments)
            except Exception as err:
                logger.error(f"Błąd podczas wykonania narzędzia [{name}]: {err}")
                return ToolResult(is_error=True, content=f"Błąd wykonania narzędzia '{name}': {err}")
        return ToolResult(is_error=True, content=f"Nieznane narzędzie: '{name}'.")
