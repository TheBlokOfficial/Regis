import asyncio
from typing import AsyncIterator, Any
from shared import ChatResponseDTO, Event, EventBus, get_logger
from server.agent.backend import BaseLLMProvider, LLMMessage, LLMResponse, OllamaProvider
from server.agent.context import ContextBuilder
from server.agent.memory import MemoryManager
from server.events import ServerEventType

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
        event_bus: EventBus | None = None,
    ) -> None:
        self.llm_provider: BaseLLMProvider = llm_provider or OllamaProvider()
        self.memory_manager: MemoryManager = memory_manager or MemoryManager()
        self.context_builder: ContextBuilder = context_builder or ContextBuilder()
        self.event_bus: EventBus = event_bus or EventBus()
        self._active_tasks: dict[str, asyncio.Task[Any]] = {}
        self._generation_buffers: dict[str, str] = {}

    def is_session_busy(self, session_id: str) -> bool:
        """Sprawdza, czy dla podanej sesji trwa obecnie przetwarzanie w tle."""
        task = self._active_tasks.get(session_id)
        return task is not None and not task.done()

    def get_generation_buffer(self, session_id: str) -> str | None:
        """Zwraca bufor obecnie generowanego tekstu dla danej sesji lub None, jeśli brak aktywnej generacji."""
        if self.is_session_busy(session_id):
            return self._generation_buffers.get(session_id, "")
        return None

    def get_session_generation_status(self, session_id: str) -> dict[str, Any]:
        """Zwraca metadane określające status trwającej generacji w sesji."""
        busy = self.is_session_busy(session_id)
        return {
            "is_generating": busy,
            "buffer": self._generation_buffers.get(session_id, "") if busy else None,
        }

    async def cancel_interaction(self, session_id: str) -> bool:
        """Anuluje aktywne zadanie generowania odpowiedzi dla podanej sesji (dla wszystkich interfejsów).

        :param session_id: Identyfikator sesji.
        :return: True jeśli zapytanie zostało anulowane, False jeśli sesja nie była zajęta.
        """
        task = self._active_tasks.get(session_id)
        if task and not task.done():
            logger.info(f"Anulowanie aktywnego zadania dla sesji '{session_id}'...")
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            return True
        return False

    async def initialize(self) -> None:
        """Inicjalizacja rdzenia agenta."""
        logger.info("Inicjalizacja Agent Engine Kernel...")
        logger.info("Agent Engine jest gotowy.")

    async def shutdown(self) -> None:
        """Bezpieczne zamknięcie rdzenia agenta."""
        logger.info("Zamykanie Agent Engine...")
        for session_id in list(self._active_tasks.keys()):
            await self.cancel_interaction(session_id)

    async def _generate_in_background(
        self,
        session_id: str,
        prompt: str,
        system_prompt: str | None = None,
    ) -> None:
        """Wykonywane w tle zadanie generowania odpowiedzi LLM dla sesji.

        Postęp i zakończenie generacji są rozgłaszane wyłącznie przez `EventBus`
        (zdarzenia `ServerEventType.CHAT_*`) — nie ma tu bezpośredniej znajomości
        odbiorców (SSE, przyszłe WebSockets satelitów itd.).
        """
        # 1. Rejestracja pytania użytkownika w pamięci sesji (I/O na dysku poza event loopem)
        await asyncio.to_thread(self.memory_manager.add_message, session_id=session_id, role="user", content=prompt)

        # 2. Pobranie aktualnej historii i zbudowanie kontekstu LLM
        history = self.memory_manager.get_history(session_id=session_id)
        llm_messages = self.context_builder.build_messages(
            session_history=history,
            system_prompt_override=system_prompt,
        )

        self._generation_buffers[session_id] = ""

        try:
            # 3. Strumieniowanie odpowiedzi oraz agregacja pełnego tekstu
            async for chunk in self.llm_provider.generate_stream(llm_messages):
                self._generation_buffers[session_id] = self._generation_buffers.get(session_id, "") + chunk
                await self.event_bus.publish(
                    Event(type=ServerEventType.CHAT_CHUNK, payload={"session_id": session_id, "chunk": chunk}, sender="agent_engine")
                )

            # 4. Po zakończeniu strumienia, zapisujemy skompletowaną odpowiedź w sesji
            full_assistant_text = self._generation_buffers.get(session_id, "")
            await asyncio.to_thread(
                self.memory_manager.add_message,
                session_id=session_id,
                role="assistant",
                content=full_assistant_text,
            )

            await self.event_bus.publish(
                Event(type=ServerEventType.CHAT_DONE, payload={"session_id": session_id}, sender="agent_engine")
            )

        except asyncio.CancelledError:
            logger.info(f"Generowanie odpowiedzi dla sesji '{session_id}' zostało przerwane.")
            partial_text = self._generation_buffers.get(session_id, "")
            if partial_text.strip():
                await asyncio.to_thread(
                    self.memory_manager.add_message,
                    session_id=session_id,
                    role="assistant",
                    content=partial_text + " [Przerwano]",
                )
            await self.event_bus.publish(
                Event(type=ServerEventType.CHAT_CANCELLED, payload={"session_id": session_id}, sender="agent_engine")
            )
            raise
        except Exception as err:
            logger.error(f"Błąd podczas generowania odpowiedzi dla sesji '{session_id}': {err}")
            # Utrwalamy odpowiedź błędu sparowaną z pytaniem użytkownika, by historia
            # nigdy nie zostawiała nieodpowiedzianej wiadomości użytkownika w kontekście.
            await asyncio.to_thread(
                self.memory_manager.add_message,
                session_id=session_id,
                role="assistant",
                content=f"[Błąd generowania odpowiedzi: {err}]",
                metadata={"is_error": True},
            )
            await self.event_bus.publish(
                Event(type=ServerEventType.CHAT_ERROR, payload={"session_id": session_id, "error": str(err)}, sender="agent_engine")
            )
            raise
        finally:
            self._active_tasks.pop(session_id, None)
            self._generation_buffers.pop(session_id, None)

    async def interact_stream(
        self,
        session_id: str = "session_default",
        prompt: str = "",
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Główna strumieniowa pętla konwersacyjna. Utrwala zapytanie i odpowiedź w pamięci sesji.

        Subskrybuje zdarzenia `EventBus` dotyczące tej konkretnej sesji na czas trwania
        strumieniowania i tłumaczy je z powrotem na strumień tokenów dla wywołującego.

        :param session_id: Identyfikator sesji backendowej.
        :param prompt: Nowa treść wiadomości użytkownika.
        :param system_prompt: Opcjonalne nadpisanie instrukcji systemowych.
        :yields: Kolejne fragmenty tekstu (tokeny/chunking).
        """
        if self.is_session_busy(session_id):
            logger.warning(f"Sesja '{session_id}' jest zajęta. Odrzucono nakładające się zapytanie.")
            raise RuntimeError(f"Sesja '{session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.")

        logger.info(f"Strumieniowa interakcja [Sesja: '{session_id}']: '{prompt}'")

        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        async def on_chunk(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(("chunk", event.payload.get("chunk", "")))

        async def on_done(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(("done", None))

        async def on_error(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(("error", event.payload.get("error", "Nieznany błąd generowania.")))

        async def on_cancelled(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(("cancelled", None))

        self.event_bus.subscribe(ServerEventType.CHAT_CHUNK, on_chunk)
        self.event_bus.subscribe(ServerEventType.CHAT_DONE, on_done)
        self.event_bus.subscribe(ServerEventType.CHAT_ERROR, on_error)
        self.event_bus.subscribe(ServerEventType.CHAT_CANCELLED, on_cancelled)

        bg_task = asyncio.create_task(
            self._generate_in_background(
                session_id=session_id,
                prompt=prompt,
                system_prompt=system_prompt,
            )
        )
        self._active_tasks[session_id] = bg_task

        try:
            while True:
                kind, value = await queue.get()
                if kind == "chunk":
                    yield value
                elif kind == "done":
                    break
                elif kind == "cancelled":
                    raise asyncio.CancelledError()
                elif kind == "error":
                    raise RuntimeError(value)
        finally:
            self.event_bus.unsubscribe(ServerEventType.CHAT_CHUNK, on_chunk)
            self.event_bus.unsubscribe(ServerEventType.CHAT_DONE, on_done)
            self.event_bus.unsubscribe(ServerEventType.CHAT_ERROR, on_error)
            self.event_bus.unsubscribe(ServerEventType.CHAT_CANCELLED, on_cancelled)

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
        _ = [chunk async for chunk in self.interact_stream(session_id=session_id, prompt=prompt, system_prompt=system_prompt)]

        session = self.memory_manager.get_or_create_session(session_id)
        last_message = session.messages[-1]

        return ChatResponseDTO(
            session_id=session_id,
            message=last_message,
            model=getattr(self.llm_provider, "model", None),
        )
