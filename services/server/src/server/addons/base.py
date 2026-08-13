"""Wspólna infrastruktura dostępna dla dowolnego addonu (Warstwa 1).

Kernel nigdy nie importuje niczego z tego modułu — nie wie i nie musi wiedzieć,
że `BaseTool` istnieje, bo widzi wyłącznie finalną listę `ToolDefinition`
zwróconą przez `AddonProvider.build_tools()`. To czysto addonowa wygoda
implementacyjna, niezwiązana z żadną konkretną domeną (smart home czy inną) —
stąd żyje na poziomie pakietu `addons/`, a nie wewnątrz jednego konkretnego addonu.
"""

from abc import ABC, abstractmethod
from typing import Any

from server.agent.backend import ToolDefinition, ToolResult


class BaseTool(ABC):
    """Abstrakcyjna klasa bazowa dla pojedynczego narzędzia dostępnego dla LLM."""

    @property
    @abstractmethod
    def definition(self) -> ToolDefinition:
        """Specyfikacja narzędzia (nazwa, opis, schemat parametrów) przekazywana do LLM."""
        pass

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Wykonuje narzędzie z podanymi argumentami (zwalidowanymi wcześniej przez LLM)."""
        pass
