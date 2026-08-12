from typing import AsyncIterator
from shared import get_logger
from server.agent.backend import BaseLLMProvider, LLMMessage, LLMResponse, OllamaProvider

logger = get_logger("regis.agent")


class AgentEngine:
    """Rdzeń Systemu Operacyjnego Agenta AI (Agent OS Kernel).

    Zarządza stanem agenta, interakcją z modelem LLM oraz podsystemami.
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider | None = None,
    ) -> None:
        self.llm_provider: BaseLLMProvider = llm_provider or OllamaProvider()

    async def initialize(self) -> None:
        """Inicjalizacja rdzenia agenta."""
        logger.info("Inicjalizacja Agent Engine Kernel...")
        logger.info("Agent Engine jest gotowy.")

    async def shutdown(self) -> None:
        """Bezpieczne zamknięcie rdzenia agenta."""
        logger.info("Zamykanie Agent Engine...")

    async def process_prompt(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """Przetwarza zapytanie tekstowe i zwraca odpowiedź z dostawcy LLM.

        :param prompt: Treść zapytania.
        :param system_prompt: Opcjonalne wytyczne systemowe.
        :return: Wygenerowana obiektowa odpowiedź LLMResponse.
        """
        messages: list[LLMMessage] = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))

        messages.append(LLMMessage(role="user", content=prompt))

        logger.info(f"Przetwarzanie zapytania: '{prompt}'")
        return await self.llm_provider.generate(messages)

    async def process_prompt_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Strumieniuje odpowiedź tekstową w czasie rzeczywistym z dostawcy LLM.

        :param prompt: Treść zapytania.
        :param system_prompt: Opcjonalne wytyczne systemowe.
        :yields: Kolejne fragmenty tekstu (chunks/tokens).
        """
        messages: list[LLMMessage] = []
        if system_prompt:
            messages.append(LLMMessage(role="system", content=system_prompt))

        messages.append(LLMMessage(role="user", content=prompt))

        logger.info(f"Strumieniowanie zapytania: '{prompt}'")
        async for chunk in self.llm_provider.generate_stream(messages):
            yield chunk
