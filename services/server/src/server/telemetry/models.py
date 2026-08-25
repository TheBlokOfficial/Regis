"""Kształt jednego wpisu telemetrii — czyli co dokładnie znaczy „jedno wywołanie LLM".

Jednostką zapisu jest **pojedyncze `generate_stream()`**, nie tura i nie sesja.
Powód jest w pętli ReAct: w obrębie jednej tury `TurnRunner` woła model do ośmiu
razy, a lista wiadomości rośnie między wywołaniami o wynik każdego narzędzia. Zapis
per tura sklejałby te warianty w jeden i gubił dokładnie to, po co ta telemetria
powstała — różnicę między tym, co model widział w wywołaniu #1 a #3.

Przynależność do tury i sesji jest zdenormalizowana w polach rekordu
(`turn_id`/`session_id`/`call_index`), więc widok „po sesjach" to grupowanie
w zapytaniu, a nie drugi model danych.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from server.ports.llm import LLMMessage, ToolDefinition

GenerationStatus = Literal["ok", "error", "cancelled", "no_generation"]
"""`no_generation` to tura, która skończyła się, zanim doszło do wywołania modelu
(padnięty silnik świata przy budowie kontekstu, anulowanie w pierwszej sekundzie).
Bez tego statusu najciekawsze awarie byłyby w panelu niewidoczne — nie ma po nich
żadnego żądania do zalogowania."""

_TRUNCATION_MARKER = "\n…[ucięto — rekord przekroczył limit rozmiaru]"
_MIN_CONTENT_BUDGET = 512
"""Podłoga na wiadomość przy ucinaniu: rekord ma pozostać czytelny (widać rolę,
początek treści, strukturę), nawet gdy prompt był ekstremalnie długi."""


class MessageSnapshot(BaseModel):
    """Jedna wiadomość dokładnie w postaci, w jakiej poszła do dostawcy."""

    role: str = Field(..., description="Rola wiadomości w kontekście LLM")
    content: str = Field(default="", description="Treść wiadomości")
    tool_calls: list[dict[str, Any]] | None = Field(
        default=None, description="Żądania wywołania narzędzi w wiadomości assistant"
    )
    tool_call_id: str | None = Field(default=None, description="Identyfikator wywołania dla roli tool")
    tool_name: str | None = Field(default=None, description="Nazwa narzędzia dla roli tool")


class AttemptSnapshot(BaseModel):
    """Jedna próba obsłużenia wywołania przez kandydata z łańcucha fallbacku.

    Mirror `server.ai.llm.LLMAttempt` — osobny model, bo ten trafia na dysk i do API,
    więc jego kształt jest kontraktem, a tamten jest wewnętrznym zdarzeniem routera."""

    instance_id: str
    instance_name: str
    provider_type: str
    model: str | None = None
    position: int
    outcome: str
    error: str | None = None


class GenerationRecord(BaseModel):
    """Kompletny zrzut jednego wywołania LLM."""

    created_at: float = Field(..., description="Stempel rozpoczęcia wywołania")
    session_id: str | None = Field(default=None, description="Sesja, do której należy tura")
    turn_id: str | None = Field(default=None, description="Tura; None dla wywołań spoza tury (skrypt, test)")
    call_index: int = Field(default=0, description="Numer wywołania w obrębie tury, od zera")
    sender_id: str | None = Field(default=None, description="Opaque identyfikator nadawcy tury")

    model: str | None = Field(default=None, description="Model, który realnie odpowiedział")
    provider_type: str | None = Field(default=None, description="Typ dostawcy obsługującego wywołanie")
    instance_id: str | None = Field(default=None, description="Preset backendu, który obsłużył wywołanie")
    instance_name: str | None = Field(default=None, description="Wyświetlana nazwa presetu")

    status: GenerationStatus = Field(default="ok", description="Wynik wywołania")
    finish_reason: str | None = Field(default=None, description="Powód zakończenia generacji zgłoszony przez dostawcę")
    error: str | None = Field(default=None, description="Surowa treść błędu — bez sanityzacji, patrz docs/manifest.md")

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    estimated: bool = Field(
        default=True,
        description="Czy liczniki tokenów to estymata (dostawca nie zwrócił GenerationUsage), czy realne wartości",
    )

    ttft_ms: float | None = Field(default=None, description="Czas do pierwszego zdarzenia strumienia")
    total_ms: float | None = Field(default=None, description="Łączny czas wywołania")
    output_tps: float | None = Field(default=None, description="Tokeny wyjściowe na sekundę po pierwszym tokenie")
    tool_calls: int = Field(default=0, description="Liczba żądań wywołania narzędzi w tej rundzie")

    messages: list[MessageSnapshot] = Field(default_factory=list)
    tools: list[dict[str, Any]] = Field(default_factory=list)
    attempts: list[AttemptSnapshot] = Field(default_factory=list)
    truncated: bool = Field(default=False, description="Czy treści zostały ucięte przez limit rozmiaru")

    # --- Co model wygenerował w odpowiedzi na powyższy kontekst ---------------
    #
    # Powiązanie wejścia z wyjściem nie potrzebuje żadnego klucza: rekord JEST
    # jednym `generate_stream()`, więc to, co strumień wydał, jest z definicji
    # odpowiedzią na dokładnie ten input.
    #
    # Odtworzenie tego z kolejnych rekordów **nie zadziała** i nie jest to detal:
    # runda pośrednia faktycznie wraca do modelu jako `assistant`+`tool` w kontekście
    # następnego wywołania, ale runda OSTATNIA już nie — finalna odpowiedź idzie do
    # pamięci sesji, nie do `working_messages`. Rozumowanie nie wraca nigdy i donikąd
    # (patrz `ReasoningChunk`), więc dekorator na porcie jest jedynym miejscem
    # w systemie, które je w ogóle widzi.
    answer: str = Field(default="", description="Tekst odpowiedzi wygenerowany w tej rundzie")
    reasoning: str = Field(default="", description="Monolog wewnętrzny modelu (chain of thought) z tej rundy")
    response_tool_calls: list[dict[str, Any]] = Field(
        default_factory=list, description="Żądania wywołania narzędzi wygenerowane w tej rundzie"
    )


def snapshot_messages(messages: list[LLMMessage]) -> list[MessageSnapshot]:
    """Zamraża listę wiadomości. Kopia, nie referencja — `TurnRunner` dopisuje do tej
    samej listy kolejne rundy pętli ReAct, więc referencja pokazywałaby stan końcowy
    tury zamiast stanu w momencie wywołania."""
    return [
        MessageSnapshot(
            role=m.role,
            content=m.content,
            tool_calls=(
                [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in m.tool_calls]
                if m.tool_calls
                else None
            ),
            tool_call_id=m.tool_call_id,
            tool_name=m.tool_name,
        )
        for m in messages
    ]


def snapshot_tools(tools: list[ToolDefinition] | None) -> list[dict[str, Any]]:
    """Narzędzia udostępnione modelowi w tym wywołaniu — część żądania, więc część zrzutu."""
    if not tools:
        return []
    return [{"name": t.name, "description": t.description, "parameters": t.parameters} for t in tools]


def _clip(text: str, budget: int) -> str:
    return text[:budget] + _TRUNCATION_MARKER if len(text) > budget else text


def enforce_size_limit(record: GenerationRecord, max_bytes: int) -> GenerationRecord:
    """Przycina zrzut do limitu, gdy prompt urósł ponad rozsądek.

    Ucinane są **wyłącznie treści** (wiadomości kontekstu, odpowiedź, rozumowanie) —
    struktura (ile wiadomości, w jakich rolach, z jakimi narzędziami) zostaje
    nietknięta, bo to ona niesie większość wartości diagnostycznej i to po niej
    działa porównywanie kolejnych wywołań. Budżet dzielony jest równo, więc jedna
    gigantyczna wiadomość nie wypycha wszystkich pozostałych do zera.
    """
    parts = [m.content for m in record.messages] + [record.answer, record.reasoning]
    payload_size = sum(len(part.encode("utf-8")) for part in parts)
    if payload_size <= max_bytes:
        return record

    budget = max(_MIN_CONTENT_BUDGET, max_bytes // max(1, len(parts)))
    return record.model_copy(
        update={
            "messages": [m.model_copy(update={"content": _clip(m.content, budget)}) for m in record.messages],
            "answer": _clip(record.answer, budget),
            "reasoning": _clip(record.reasoning, budget),
            "truncated": True,
        }
    )
