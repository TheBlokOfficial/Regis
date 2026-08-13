import asyncio
from typing import AsyncIterator, Any
from shared import ChatResponseDTO, Event, EventBus, get_logger
from server.agent.addon_contract import AddonProvider, ToolDispatch
from server.agent.backend import BaseLLMProvider, LLMMessage, LLMResponse, OllamaProvider, ToolCallRequest, ToolDefinition, ToolResult
from server.agent.context import ContextBuilder
from server.agent.memory import MemoryManager
from server.agent.prompts import PromptStore
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
        prompt_store: PromptStore | None = None,
        addons: list[AddonProvider] | None = None,
        max_tool_iterations: int = 8,
    ) -> None:
        self.llm_provider: BaseLLMProvider = llm_provider or OllamaProvider()
        self.memory_manager: MemoryManager = memory_manager or MemoryManager()
        self.context_builder: ContextBuilder = context_builder or ContextBuilder()
        self.event_bus: EventBus = event_bus or EventBus()
        self.prompt_store: PromptStore = prompt_store or PromptStore()
        # Kernel nie zna żadnego konkretnego addonu — pusta lista to bezpieczny domyślny
        # stan (agent działa jak zwykły chat, bez narzędzi). Kompozycja addonów należy do main.py.
        self.addons: list[AddonProvider] = addons or []
        self.max_tool_iterations: int = max_tool_iterations
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

    async def _build_aggregated_tools(self) -> tuple[list[ToolDefinition], ToolDispatch]:
        """Agreguje narzędzia ze wszystkich zarejestrowanych addonów w jeden zestaw dla LLM.

        Kernel nie wie nic o pochodzeniu narzędzi — tylko woła `build_tools()`
        na każdym addonie zgodnie z generycznym kontraktem `AddonProvider`.

        Polityka kolizji nazw: jeśli dwa addony zarejestrują narzędzie o tej
        samej nazwie, wcześniej zarejestrowany wygrywa — kolidujące narzędzie
        późniejszego addonu jest logowane jako błąd i pomijane (bez cichego nadpisania).
        """
        all_defs: list[ToolDefinition] = []
        dispatch_map: dict[str, ToolDispatch] = {}

        for addon in self.addons:
            defs, dispatch = await addon.build_tools()
            for d in defs:
                if d.name in dispatch_map:
                    logger.error(
                        f"Konflikt nazw narzędzi: '{d.name}' jest już zarejestrowane przez inny addon "
                        f"— pomijam duplikat z addonu {type(addon).__name__}."
                    )
                    continue
                dispatch_map[d.name] = dispatch
                all_defs.append(d)

        async def combined_dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            dispatch = dispatch_map.get(name)
            if dispatch is None:
                return ToolResult(is_error=True, content=f"Nieznane narzędzie: '{name}'.")
            return await dispatch(name, arguments)

        return all_defs, combined_dispatch

    async def _generate_in_background(
        self,
        session_id: str,
        prompt: str,
    ) -> None:
        """Wykonywane w tle zadanie generowania odpowiedzi LLM dla sesji.

        Realizuje pełną pętlę agentyczną (ReAct): jeśli LLM zażąda wywołania
        narzędzia, wynik wraca do niego jako kolejna wiadomość i generacja jest
        kontynuowana, aż model zwróci odpowiedź finalną (bez wywołań narzędzi)
        lub zostanie przekroczony `max_tool_iterations`. Tylko finalny,
        skumulowany tekst trafia do `MemoryManager` — pośrednie wiadomości
        `assistant`/`tool` żyją wyłącznie w lokalnej liście na czas tej interakcji.

        Postęp i zakończenie generacji są rozgłaszane wyłącznie przez `EventBus`
        (zdarzenia `ServerEventType.CHAT_*`) — nie ma tu bezpośredniej znajomości
        odbiorców (SSE, przyszłe WebSockets satelitów itd.).
        """
        # 1. Rejestracja pytania użytkownika w pamięci sesji (I/O na dysku poza event loopem)
        await asyncio.to_thread(self.memory_manager.add_message, session_id=session_id, role="user", content=prompt)

        # 2. Pobranie aktywnego promptu systemowego ze store'u (fallback do DEFAULT_SYSTEM_PROMPT w builderze)
        active_system_prompt = await self.prompt_store.get_active_content()

        self._generation_buffers[session_id] = ""

        try:
            # 3. Budowa zestawu narzędzi dostępnych agentowi na czas tej interakcji (agregacja addonów)
            tool_defs, dispatch_tool = await self._build_aggregated_tools()

            # 4. Pobranie aktualnej historii i zbudowanie kontekstu LLM
            history = self.memory_manager.get_history(session_id=session_id)
            working_messages = self.context_builder.build_messages(
                session_history=history,
                system_prompt_override=active_system_prompt,
                tools_available=bool(tool_defs),
            )

            for iteration in range(self.max_tool_iterations):
                turn_text = ""
                pending_calls: list[ToolCallRequest] = []

                async for event in self.llm_provider.generate_stream(working_messages, tools=tool_defs):
                    if isinstance(event, ToolCallRequest):
                        pending_calls.append(event)
                        continue
                    turn_text += event
                    self._generation_buffers[session_id] = self._generation_buffers.get(session_id, "") + event
                    await self.event_bus.publish(
                        Event(type=ServerEventType.CHAT_CHUNK, payload={"session_id": session_id, "chunk": event}, sender="agent_engine")
                    )

                if not pending_calls:
                    break

                working_messages.append(LLMMessage(role="assistant", content=turn_text, tool_calls=pending_calls))
                for call in pending_calls:
                    result = await dispatch_tool(call.name, call.arguments)
                    logger.info(
                        f"Wywołano narzędzie '{call.name}' [sesja: '{session_id}']: "
                        f"{'błąd' if result.is_error else 'ok'}"
                    )
                    working_messages.append(
                        LLMMessage(role="tool", content=result.content, tool_call_id=call.id, tool_name=call.name)
                    )
            else:
                logger.warning(
                    f"Przekroczono limit {self.max_tool_iterations} iteracji pętli agentycznej "
                    f"dla sesji '{session_id}'. Finalizowanie z dotychczasową odpowiedzią."
                )

            # 5. Po zakończeniu pętli zapisujemy skompletowaną odpowiedź w sesji
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
    ) -> AsyncIterator[str]:
        """Główna strumieniowa pętla konwersacyjna. Utrwala zapytanie i odpowiedź w pamięci sesji.

        Subskrybuje zdarzenia `EventBus` dotyczące tej konkretnej sesji na czas trwania
        strumieniowania i tłumaczy je z powrotem na strumień tokenów dla wywołującego.

        :param session_id: Identyfikator sesji backendowej.
        :param prompt: Nowa treść wiadomości użytkownika.
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
    ) -> ChatResponseDTO:
        """Ścisła, niestrumieniowa konwersacja bazująca bezpośrednio na strumieniowej pętli (DRY wrapper).

        :param session_id: Identyfikator sesji backendowej.
        :param prompt: Nowa treść wiadomości użytkownika.
        :return: Struktura ChatResponseDTO z wygenerowaną odpowiedzią i nazwą modelu.
        """
        _ = [chunk async for chunk in self.interact_stream(session_id=session_id, prompt=prompt)]

        session = self.memory_manager.get_or_create_session(session_id)
        last_message = session.messages[-1]

        return ChatResponseDTO(
            session_id=session_id,
            message=last_message,
            model=getattr(self.llm_provider, "model", None),
        )
