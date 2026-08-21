"""Jedyny kontrakt granicy Kernel <-> Świat (dawna Warstwa 0 <-> Warstwa 1).

Kernel zna wyłącznie ten protokół — nigdy `server.world` po nazwie. `tool_definitions`
i `dispatch` są ustrukturyzowane, bo kernel ich mechanicznie potrzebuje (schemat
API dostawcy LLM, wywołanie funkcji) — `system_prompt` to pojedynczy, już gotowy
opaque string: jeśli implementacja `WorldInterface` go dostarcza, to jest to
KOMPLETNY prompt tej tury (World jest jedynym autorem — sam dokleja swoją
tożsamość do dynamicznych faktów, kernel niczego nie skleja). `None` oznacza,
że World nie ma nic do powiedzenia (albo nie jest podłączony) — kernel wtedy
używa własnego, prostego fallbacku (`agent/prompts/`). Ten podział celowo
unika sytuacji, w której dwóch niepowiązanych autorów (kernel + World) musi
nieformalnie respektować wspólną hierarchię formatowania (Markdown, nagłówki)
przy sklejaniu dwóch fragmentów.
"""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol

from server.agent.llm import ToolDefinition, ToolResult

ToolDispatch = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


@dataclass
class ContextBuild:
    """Pełny wkład silnika świata na czas jednej interakcji agenta."""

    tool_definitions: list[ToolDefinition]
    system_prompt: str | None
    dispatch: ToolDispatch


class WorldInterface(Protocol):
    """Jedyny byt, z którym rozmawia kernel — analogicznie do `BaseLLMProvider`
    względem konkretnych dostawców: kernel zna kształt, nigdy implementację."""

    async def build(self, sender_id: str | None = None, voice_mode: bool = False) -> ContextBuild:
        """Buduje pełny wkład na czas jednej interakcji agenta.

        :param sender_id: Opaque identyfikator nadawcy (np. satelity) —
            nieinterpretowany przez kernel, przekazywany dalej bez zmian.
        :param voice_mode: Mechaniczna flaga wywołania (dostarczana przez
            gateway, który jako jedyny wie to z całą pewnością — np.
            `server.voice`) — nieinterpretowana przez kernel, tylko przekazywana
            dalej. Treść ewentualnego frazowania głosowego to wyłączna
            odpowiedzialność implementacji `WorldInterface`.
        """
        ...


class NullWorldInterface:
    """Domyślna, pusta implementacja — `AgentEngine` działa samodzielnie (zwykły
    chat bez narzędzi) bez importowania żadnej domeny. Zachowuje przenośność
    kernela: `agent/`+`memory/`+`context/`+`backend/`+`prompts/` da się wyjąć do
    innej aplikacji bez ciągnięcia za sobą `server.world`."""

    async def build(self, sender_id: str | None = None, voice_mode: bool = False) -> ContextBuild:
        del sender_id, voice_mode

        async def _dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            del arguments
            return ToolResult(is_error=True, content=f"Brak dostępnych narzędzi — narzędzie '{name}' niedostępne.")

        return ContextBuild(tool_definitions=[], system_prompt=None, dispatch=_dispatch)
