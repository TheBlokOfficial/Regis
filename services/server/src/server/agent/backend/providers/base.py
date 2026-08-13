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


@dataclass
class LLMMessage:
    """Struktura pojedynczej wiadomości w konwersacji z dostawcą LLM."""

    role: Literal["system", "user", "assistant", "tool"]
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
    ) -> AsyncIterator[str | ToolCallRequest]:
        """Strumieniuje wygenerowane fragmenty tekstu oraz żądania wywołania narzędzi.

        :param messages: Lista wiadomości stanowiących kontekst konwersacji.
        :param tools: Opcjonalna lista narzędzi udostępnionych LLM do wywołania.
        :param kwargs: Dodatkowe opcjonalne parametry generacji.
        :yields: Fragmenty tekstu (`str`) lub kompletne żądania wywołania narzędzia (`ToolCallRequest`).
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
            if isinstance(event, str):
                chunks.append(event)

        full_content = "".join(chunks)
        model_name = getattr(self, "model", "unknown")
        return LLMResponse(content=full_content, model=model_name)

    @abstractmethod
    async def check_health(self) -> bool:
        """Sprawdza dostępność dostawcy LLM.

        :return: True jeśli połączenie z dostawcą jest aktywne i gotowe, w przeciwnym razie False.
        """
        pass
