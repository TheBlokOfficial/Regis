from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal


@dataclass
class LLMMessage:
    """Struktura pojedynczej wiadomości w konwersacji z dostawcą LLM."""

    role: Literal["system", "user", "assistant"]
    content: str


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

    @abstractmethod
    def generate_stream(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Strumieniuje wygenerowane fragmenty tekstu (tokeny/słowa) w czasie rzeczywistym.

        :param messages: Lista wiadomości stanowiących kontekst konwersacji.
        :param kwargs: Dodatkowe opcjonalne parametry generacji.
        :yields: Kolejne fragmenty tekstu (chunks/tokens) generowane przez dostawcę.
        """
        pass

    async def generate(
        self,
        messages: list[LLMMessage],
        **kwargs: Any,
    ) -> LLMResponse:
        """Generuje pełną odpowiedź z dostawcy LLM, sklejając tokeny ze strumienia.

        :param messages: Lista wiadomości stanowiących kontekst konwersacji.
        :param kwargs: Dodatkowe opcjonalne parametry generacji.
        :return: Wygenerowana obiektowo odpowiedź typu LLMResponse.
        """
        chunks: list[str] = []
        async for chunk in self.generate_stream(messages, **kwargs):
            chunks.append(chunk)

        full_content = "".join(chunks)
        model_name = getattr(self, "model", "unknown")
        return LLMResponse(content=full_content, model=model_name)

    @abstractmethod
    async def check_health(self) -> bool:
        """Sprawdza dostępność dostawcy LLM.

        :return: True jeśli połączenie z dostawcą jest aktywne i gotowe, w przeciwnym razie False.
        """
        pass
