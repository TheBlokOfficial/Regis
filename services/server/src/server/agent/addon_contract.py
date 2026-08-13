"""Generyczny kontrakt granicy Warstwa 0 (kernel) <-> Warstwa 1 (addony).

Kernel zna wyłącznie ten protokół — nigdy konkretnego addonu (np. Smart Home).
Addon nie musi nawet importować tego modułu, wystarczy że strukturalnie
pasuje kształtem (typing.Protocol — strukturalne typowanie).
"""

from typing import Any, Awaitable, Callable, Protocol

from server.agent.backend import ToolDefinition, ToolResult

ToolDispatch = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


class AddonProvider(Protocol):
    """Cokolwiek dostarczające agentowi zestaw wywoływalnych narzędzi."""

    async def build_tools(self) -> tuple[list[ToolDefinition], ToolDispatch]:
        """Buduje pełny zestaw narzędzi tego addonu na czas jednej interakcji agenta."""
        ...
