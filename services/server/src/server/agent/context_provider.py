"""Jedyny kontrakt granicy Kernel <-> Świat (dawna Warstwa 0 <-> Warstwa 1).

Kernel zna wyłącznie ten protokół — nigdy `server.world` po nazwie. `tool_definitions`
i `dispatch` są ustrukturyzowane, bo kernel ich mechanicznie potrzebuje (schemat
API dostawcy LLM, wywołanie funkcji) — cała reszta dynamicznej treści promptu to
jeden opaque blok prozy (`dynamic_context`), którego kształt/formatowanie jest
wyłączną odpowiedzialnością implementacji `WorldInterface`, nigdy kernela.
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from server.agent.backend import ToolDefinition, ToolResult

ToolDispatch = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


@dataclass
class ContextBuild:
    """Pełny wkład silnika świata na czas jednej interakcji agenta."""

    tool_definitions: list[ToolDefinition]
    dynamic_context: str
    dispatch: ToolDispatch


class WorldInterface(Protocol):
    """Jedyny byt, z którym rozmawia kernel — analogicznie do `BaseLLMProvider`
    względem konkretnych dostawców: kernel zna kształt, nigdy implementację."""

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        """Buduje pełny wkład na czas jednej interakcji agenta.

        :param sender_id: Opaque identyfikator nadawcy (np. satelity) —
            nieinterpretowany przez kernel, przekazywany dalej bez zmian.
        """
        ...


class NullWorldInterface:
    """Domyślna, pusta implementacja — `AgentEngine` działa samodzielnie (zwykły
    chat bez narzędzi) bez importowania żadnej domeny. Zachowuje przenośność
    kernela: `agent/`+`memory/`+`context/`+`backend/`+`prompts/` da się wyjąć do
    innej aplikacji bez ciągnięcia za sobą `server.world`."""

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        del sender_id

        async def _dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            del arguments
            return ToolResult(is_error=True, content=f"Brak dostępnych narzędzi — narzędzie '{name}' niedostępne.")

        return ContextBuild(tool_definitions=[], dynamic_context="", dispatch=_dispatch)
