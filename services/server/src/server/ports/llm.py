"""Port LLM oraz "język", w jakim cały system rozmawia o narzędziach.

Konkretni dostawcy (`OllamaProvider`, `OpenAICompatibleProvider`) i logika wyboru
(`BackendRegistry`/`LLMFactory`/`LLMRouter`) mieszkają w `server.ai.llm`;
konsumentem protokołu jest kernel (`server.agent`), a `ToolDefinition`/`ToolResult`
używa też `server.world`. Protokół stoi w `ports/`, żeby żadna z tych stron nie
musiała importować pozostałych (patrz `ports/__init__.py`).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal


@dataclass
class ToolCallRequest:
    """Kompletne żądanie wywołania narzędzia wygenerowane przez LLM.

    Providerzy buforują wewnętrznie fragmentaryczny format swojego API (np. SSE
    delty OpenAI-compatible) i yieldują tę strukturę dopiero w całości —
    warstwa agenta nigdy nie zna surowego formatu konkretnego dostawcy.
    """

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ReasoningChunk:
    """Fragment *rozumowania* modelu (chain of thought), nie treści odpowiedzi.

    Osobny typ, a nie string ze znacznikiem w treści (`<think>…</think>`, jak było
    wcześniej): rodzaj tokena to fakt strukturalny, a przemycanie go w tekście gubiło
    tę informację natychmiast po opuszczeniu providera. Konsekwencje tamtego modelu
    były realne i wszystkie z jednego korzenia — TTS czytał rozumowanie na głos,
    chain of thought lądował w pamięci sesji i wracał do modelu w każdej kolejnej
    turze, a Web UI musiało odzyskiwać podział parsując strumień znak po znaku.

    Kto nie potrafi tego wyświetlić/wypowiedzieć, po prostu pomija ten typ —
    `isinstance(event, str)` nadal jednoznacznie znaczy "tekst odpowiedzi".
    """

    text: str


@dataclass
class ToolDefinition:
    """Specyfikacja narzędzia udostępnianego LLM (JSON Schema parametrów)."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass
class ToolResult:
    """Wynik wykonania narzędzia zwracany do LLM w kolejnej turze pętli agentycznej.

    Symetryczny odpowiednik `ToolCallRequest` — razem tworzą "język" w jakim
    kernel rozmawia o narzędziach z LLM, niezależnie od tego, jaki addon
    faktycznie wykonał narzędzie.
    """

    content: str
    is_error: bool = False
    redirect_sender_id: str | None = None
    """Opaque cel przekierowania dalszej dostawy odpowiedzi (np. `WorldEngine.speak_in_room`).

    Kernel nie interpretuje znaczenia tego pola — traktuje je wyłącznie
    mechanicznie, jako nowy tag publikacji zdarzeń `EventBus` dla reszty tej
    tury (`agent/engine.py`, `_generate_in_background`). Semantyka ("dlaczego
    przekierowano") to wyłączna wiedza silnika świata, który je ustawił."""


LLMRole = Literal["system", "user", "assistant", "tool"]
"""Role, jakie rozumie dostawca LLM. Alias, a nie literał w miejscu użycia —
`ContextBuilder` musi jawnie zawęzić do niego `str` z pamięci sesji, a bez
wspólnej nazwy to zawężenie kopiowałoby listę wartości."""


@dataclass
class LLMMessage:
    """Struktura pojedynczej wiadomości w konwersacji z dostawcą LLM."""

    role: LLMRole
    content: str
    tool_calls: list[ToolCallRequest] | None = None
    tool_call_id: str | None = None
    tool_name: str | None = None


@dataclass
class LLMResponse:
    """Struktura odpowiedzi zwróconej przez dostawcę LLM."""

    content: str
    model: str
    raw_response: dict[str, Any] = field(default_factory=dict)


class BaseLLMProvider(ABC):
    """Abstrakcyjna klasa bazowa dla dostawców modeli LLM."""

    @property
    def model(self) -> str:
        """Domyślna nazwa modelu obsługiwanego przez dostawcę."""
        return getattr(self, "_model", "unknown")

    @property
    def max_tokens(self) -> int | None:
        """Limit tokenów wyjściowych wygenerowanej odpowiedzi."""
        return getattr(self, "_max_tokens", None)

    @abstractmethod
    def generate_stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | ReasoningChunk | ToolCallRequest]:
        """Strumieniuje fragmenty odpowiedzi, rozumowania oraz żądania wywołania narzędzi.

        :param messages: Lista wiadomości stanowiących kontekst konwersacji.
        :param tools: Opcjonalna lista narzędzi udostępnionych LLM do wywołania.
        :param kwargs: Dodatkowe opcjonalne parametry generacji.
        :yields: Fragmenty tekstu odpowiedzi (`str`), fragmenty rozumowania
            (`ReasoningChunk`) lub kompletne żądania wywołania narzędzia (`ToolCallRequest`).
        """
        pass

    async def generate(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Generuje pełną odpowiedź z dostawcy LLM, sklejając tokeny ze strumienia.

        :param messages: Lista wiadomości stanowiących kontekst konwersacji.
        :param tools: Opcjonalna lista narzędzi udostępnionych LLM do wywołania.
        :param kwargs: Dodatkowe opcjonalne parametry generacji.
        :return: Wygenerowana obiektowo odpowiedź typu LLMResponse.
        """
        chunks: list[str] = []
        async for event in self.generate_stream(messages, tools=tools, **kwargs):
            # `ReasoningChunk`/`ToolCallRequest` odpadają same — `str` to wyłącznie
            # tekst odpowiedzi, więc rozumowanie nigdy nie wycieka do `LLMResponse`.
            if isinstance(event, str):
                chunks.append(event)

        full_content = "".join(chunks)
        model_name = getattr(self, "model", "unknown")
        return LLMResponse(content=full_content, model=model_name)
