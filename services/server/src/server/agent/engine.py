import asyncio
from typing import AsyncIterator, Any
from shared import ChatResponseDTO, get_logger
from server.agent.backend import BaseLLMProvider, LLMMessage, LLMResponse, OllamaProvider
from server.agent.context import ContextBuilder
from server.agent.memory import MemoryManager

logger = get_logger("regis.agent")


class AgentEngine:
    """Rdzeń Systemu Operacyjnego Agenta AI (Agent OS Kernel).

    Zarządza stanem agenta, pamięcią sesji, budowaniem kontekstu oraz interakcją z LLM.
    """

    def __init__(
        self,
        llm_provider: BaseLLMProvider | None = None,
        memory_manager: MemoryManager | None = None,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.llm_provider: BaseLLMProvider = llm_provider or OllamaProvider()
        self.memory_manager: MemoryManager = memory_manager or MemoryManager()
        self.context_builder: ContextBuilder = context_builder or ContextBuilder()
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}

    def is_session_busy(self, session_id: str) -> bool:
        """Sprawdza, czy dla podanej sesji trwa obecnie przetwarzanie w tle."""
        task = self._active_tasks.get(session_id)
        return task is not None and not task.done()

    async def cancel_interaction(self, session_id: str) -> bool:
        """Anuluje aktywne zadanie generowania odpowiedzi dla podanej sesji (dla wszystkich interfejsów).

        :param session_id: Identyfikator sesji.
        :return: True jeśli zapytanie zostało anulowane, False jeśli sesja nie była zajęta.
        """
        task = self._active_tasks.get(session_id)
        if task and not task.done():
            logger.info(f"Anulowanie aktywnego zadania dla sesji '{session_id}'...")
            task.cancel()
            return True
        return False

    async def initialize(self) -> None:
        """Inicjalizacja rdzenia agenta."""
        logger.info("Inicjalizacja Agent Engine Kernel...")
        logger.info("Agent Engine jest gotowy.")

    async def shutdown(self) -> None:
        """Bezpieczne zamknięcie rdzenia agenta."""
        logger.info("Zamykanie Agent Engine...")

    async def interact_stream(
        self,
        session_id: str = "session_default",
        prompt: str = "",
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Główna strumieniowa pętla konwersacyjna. Utrwala zapytanie i odpowiedź w pamięci sesji.

        :param session_id: Identyfikator sesji backendowej.
        :param prompt: Nowa treść wiadomości użytkownika.
        :param system_prompt: Opcjonalne nadpisanie instrukcji systemowych.
        :yields: Kolejne fragmenty tekstu (tokeny/chunking).
        """
        if self.is_session_busy(session_id):
            logger.warning(f"Sesja '{session_id}' jest zajęta. Odrzucono nakładające się zapytanie.")
            raise RuntimeError(f"Sesja '{session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.")

        current_task = asyncio.current_task()
        if current_task:
            self._active_tasks[session_id] = current_task

        logger.info(f"Strumieniowa interakcja [Sesja: '{session_id}']: '{prompt}'")

        # 1. Rejestracja pytania użytkownika w pamięci sesji
        self.memory_manager.add_message(session_id=session_id, role="user", content=prompt)

        # 2. Pobranie aktualnej historii i zbudowanie kontekstu LLM
        history = self.memory_manager.get_history(session_id=session_id)
        llm_messages = self.context_builder.build_messages(
            session_history=history,
            system_prompt_override=system_prompt,
        )

        full_chunks: list[str] = []
        try:
            # 3. Strumieniowanie odpowiedzi oraz agregacja pełnego tekstu
            async for chunk in self.llm_provider.generate_stream(llm_messages):
                full_chunks.append(chunk)
                yield chunk

            # 4. Po zakończeniu strumienia, zapisujemy skompletowaną odpowiedź w sesji
            full_assistant_text = "".join(full_chunks)
            self.memory_manager.add_message(
                session_id=session_id,
                role="assistant",
                content=full_assistant_text,
            )
        except asyncio.CancelledError:
            logger.info(f"Generowanie odpowiedzi dla sesji '{session_id}' zostało przerwane.")
            partial_text = "".join(full_chunks)
            if partial_text.strip():
                self.memory_manager.add_message(
                    session_id=session_id,
                    role="assistant",
                    content=partial_text + " [Przerwano]",
                )
            raise
        finally:
            self._active_tasks.pop(session_id, None)

    async def interact(
        self,
        session_id: str = "session_default",
        prompt: str = "",
        system_prompt: str | None = None,
    ) -> ChatResponseDTO:
        """Ścisła, niestrumieniowa konwersacja bazująca bezpośrednio na strumieniowej pętli (DRY wrapper).

        :param session_id: Identyfikator sesji backendowej.
        :param prompt: Nowa treść wiadomości użytkownika.
        :param system_prompt: Opcjonalne nadpisanie instrukcji systemowych.
        :return: Struktura ChatResponseDTO z wygenerowaną odpowiedzią i nazwą modelu.
        """
        # Wywołanie głównej pętli strumieniowej i zgromadzenie fragmentów odpowiedzi
        _ = [chunk async for chunk in self.interact_stream(session_id=session_id, prompt=prompt, system_prompt=system_prompt)]
        
        session = self.memory_manager.get_or_create_session(session_id)
        last_message = session.messages[-1]

        return ChatResponseDTO(
            session_id=session_id,
            message=last_message,
            model=getattr(self.llm_provider, "model", None),
        )

