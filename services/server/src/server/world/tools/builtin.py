"""Narzędzia własne Świata — niezależne od Home Assistanta.

`get_time` jest dowodem **zasady symetrii Fakt↔narzędzie** (`docs/manifest.md`,
sekcja 5): ta sama wartość, którą sekcje kontekstu wstawiają proaktywnie w miejsce
`{czas}`, jest też dostępna reaktywnie, przez wywołanie — i liczona z tego samego
`datetime.now()` w obrębie jednej tury, więc nie da się ich rozjechać.

`speak_in_room` widzi wyłącznie **pokój**, nigdy `sender_id`: ten sam słownik, co
nagłówki listy urządzeń. Opaque identyfikator klienta nie ma prawa wyciec do promptu
(zasada „adresowanie po natywnym ID/etykiecie, nie po opaque ID").
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from server.ports.llm import ToolDefinition, ToolResult
from server.world.models import SenderProfile
from server.world.prompt_sections import PromptSectionsConfig, TurnFacts
from server.world.tools.registry import Tool
from server.world.turn_context import sections_gained_after_redirect

GET_TIME_TOOL = "get_time"
SPEAK_IN_ROOM_TOOL = "speak_in_room"

SpeakerFinder = Callable[[str], Awaitable[tuple[str | None, list[str]]]]
"""Nazwa pokoju -> (`sender_id` jednoznacznego odbiornika z głośnikiem, kandydaci przy
niejednoznaczności). Wstrzykiwane przez silnik, żeby narzędzie nie znało rejestrów."""

TargetDescriber = Callable[[str], Awaitable[tuple[SenderProfile | None, str | None]]]
"""`sender_id` -> (profil klienta, nazwa jego pokoju) — potrzebne do przeliczenia sekcji
dla nowego celu dostawy."""


def get_time_tool(now: str) -> Tool:
    """:param now: ta sama wartość, którą dostały sekcje kontekstu tej tury."""
    return Tool(
        definition=ToolDefinition(
            name=GET_TIME_TOOL,
            description="Zwraca aktualną datę i godzinę.",
            parameters={"type": "object", "properties": {}},
        ),
        handler=lambda _arguments: _constant(now),
    )


def speak_in_room_tool(
    find_speaker: SpeakerFinder,
    describe_target: TargetDescriber,
    sections: PromptSectionsConfig,
    facts: TurnFacts,
) -> Tool:
    """Przekierowanie dalszej części TEJ odpowiedzi do odbiornika w innym pokoju."""

    async def handler(arguments: dict[str, Any]) -> ToolResult:
        room = str(arguments.get("room", ""))
        target_sender_id, candidates = await find_speaker(room)
        if target_sender_id is None:
            if candidates:
                return ToolResult(
                    is_error=True,
                    content=f"W pokoju '{room}' jest zarejestrowanych wielu odbiorników — nie można jednoznacznie wybrać.",
                )
            return ToolResult(is_error=True, content=f"Brak odbiornika z głośnikiem w pokoju '{room}'.")

        target_profile, target_room_name = await describe_target(target_sender_id)
        # Treść wyniku niesie NOWE ramowanie dostawy — cel zmienił się w połowie tury,
        # a kontekst tury powstał przed jej startem i już tego nie nadgoni. Wyniki
        # narzędzi wracają do modelu w pętli ReAct, więc to naturalny kanał na tę korektę.
        #
        # Nie hardkodujemy tu zdania: przeliczamy sekcje użytkownika dla NOWEGO celu
        # i dokładamy tylko te, które wcześniej nie obowiązywały. Dzięki temu tekst
        # pochodzi z tej samej konfiguracji co start tury, a model nie dostaje po raz
        # drugi rzeczy, które już wie (np. listy urządzeń).
        content = f"Przełączono dalszą odpowiedź na pokój '{room}'."
        added = sections_gained_after_redirect(sections, facts, target_profile, target_room_name)
        if added:
            content = "\n\n".join([content, *added])
        return ToolResult(content=content, redirect_sender_id=target_sender_id)

    return Tool(
        definition=ToolDefinition(
            name=SPEAK_IN_ROOM_TOOL,
            description=(
                "Przełącza dalszą część TEJ odpowiedzi na odbiornik przypisany do podanego pokoju "
                "(np. przekierowanie mowy na inny głośnik). Użyj gdy użytkownik prosi o ogłoszenie/"
                "odpowiedź w innym pokoju niż ten, z którego przyszło pytanie."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "room": {
                        "type": "string",
                        "description": "Nazwa pokoju — ta sama etykieta co w nagłówkach listy urządzeń/lokalizacji.",
                    }
                },
                "required": ["room"],
            },
        ),
        handler=handler,
    )


async def _constant(content: str) -> ToolResult:
    return ToolResult(content=content)
