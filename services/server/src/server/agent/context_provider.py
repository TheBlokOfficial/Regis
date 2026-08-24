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

from server.ports.llm import ToolDefinition, ToolResult

ToolDispatch = Callable[[str, dict[str, Any]], Awaitable[ToolResult]]


@dataclass
class ContextBuild:
    """Pełny wkład silnika świata na czas jednej interakcji agenta.

    `system_prompt` i `turn_context` są rozdzielone **celowo, wzdłuż osi
    zmienności** — nie tematycznie:

    * `system_prompt` — treść, która między turami tej samej sesji się NIE
      zmienia (tożsamość, zasady). Trafia na pozycję zerową kontekstu.
    * `turn_context` — fakty prawdziwe tylko teraz (czas, stan urządzeń,
      sposób dostarczenia odpowiedzi). Trafia tuż przed pytanie użytkownika.

    Dwa powody, oba zweryfikowane w tym projekcie:

    1. **Własność treści.** Tożsamość pisze użytkownik w UI, fakty generuje
       silnik. Dopóki był to jeden sklejony string, nie dało się edytować
       jednego bez dotykania drugiego.
    2. **Stabilny prefiks żądania.** Znacznik czasu w wiadomości zerowej
       sprawiał, że każda tura wyglądała dla dostawcy jak zupełnie nowe
       żądanie — cache prefiksu nie miał się o co zaczepić. (Przy sesjach
       rzędu 10-15 tur to zysk drugorzędny, ale darmowy.)

    Efekt uboczny, celowo wykorzystany: fakty lądują blisko pytania, gdzie
    modele trzymają się ich pewniej niż treści sprzed kilkunastu wiadomości.
    """

    tool_definitions: list[ToolDefinition]
    system_prompt: str | None
    turn_context: str | None
    dispatch: ToolDispatch


class WorldInterface(Protocol):
    """Jedyny byt, z którym rozmawia kernel — analogicznie do `BaseLLMProvider`
    względem konkretnych dostawców: kernel zna kształt, nigdy implementację."""

    async def build(self, sender_id: str | None = None) -> ContextBuild:
        """Buduje pełny wkład na czas jednej interakcji agenta.

        :param sender_id: Opaque identyfikator nadawcy (np. satelity) —
            nieinterpretowany przez kernel, przekazywany dalej bez zmian.
            **Jedyne**, co kernel mówi o świecie zewnętrznym: kim jest ten klient,
            co potrafi (mikrofon/głośnik/tekst) i gdzie stoi, wie wyłącznie
            implementacja `WorldInterface` — kernel nigdy tego nie interpretuje.
            Dawny parametr `voice_mode` został usunięty właśnie dlatego: był
            mechaniczną flagą, którą bramka wejściowa musiała *przenieść* przez
            kernel, choć implementacja World i tak potrafi wyprowadzić modalność
            z profilu nadawcy.
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

        return ContextBuild(tool_definitions=[], system_prompt=None, turn_context=None, dispatch=_dispatch)
