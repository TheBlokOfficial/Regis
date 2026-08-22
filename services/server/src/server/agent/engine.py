import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Any, Literal, TypedDict
from shared import ChatResponseDTO, Event, EventBus, get_logger
from server.agent.llm import BaseLLMProvider, LLMMessage, LLMResponse, ToolCallRequest
from server.ai.llm import OllamaProvider
from server.agent.context import ContextBuilder
from server.agent.context_provider import NullWorldInterface, WorldInterface
from server.agent.memory import MemoryManager
from server.agent.prompts import AgentDefaultPromptStore
from server.events import ServerEventType

logger = get_logger("regis.agent")


class ToolStepPayload(TypedDict):
    """Pojedynczy wpis kroku pętli ReAct w kolejności chronologicznej.

    `text_offset` to długość dotychczas zakumulowanego tekstu finalnej
    odpowiedzi assistant w momencie wystąpienia kroku — pozwala frontendowi
    wpleść node kroku między segmenty tekstu, zarówno w strumieniu live, jak
    i przy replayu z `ChatMessageDTO.metadata["steps"]`. Kształt płaski (pola
    zawsze obecne, `None` gdy nieużywane w danym wariancie) zamiast opcjonalnych
    kluczy — prostszy do konsumpcji bez rozgałęzień w JS.
    """

    type: Literal["tool_call", "tool_result"]
    call_id: str
    name: str
    text_offset: int
    arguments: dict[str, Any] | None
    content: str | None
    is_error: bool | None


@dataclass
class StreamEvent:
    """Ustrukturyzowany element strumienia `interact_stream` — jeden do jednego
    z rodzajem zdarzenia `EventBus`, gotowy do serializacji SSE przez wywołującego."""

    type: Literal["user_message", "chunk", "tool_start", "tool_result", "done", "error", "cancelled"]
    payload: dict[str, Any]


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
        prompt_store: AgentDefaultPromptStore | None = None,
        world: WorldInterface | None = None,
        max_tool_iterations: int = 8,
    ) -> None:
        self.llm_provider: BaseLLMProvider = llm_provider or OllamaProvider()
        self.memory_manager: MemoryManager = memory_manager or MemoryManager()
        self.context_builder: ContextBuilder = context_builder or ContextBuilder()
        self.event_bus: EventBus = event_bus or EventBus()
        self.prompt_store: AgentDefaultPromptStore = prompt_store or AgentDefaultPromptStore()
        # Kernel nie zna żadnej konkretnej implementacji — pusty NullWorldInterface to
        # bezpieczny domyślny stan (agent działa jak zwykły chat, bez narzędzi).
        # Kompozycja konkretnego silnika świata (server.world) należy do main.py.
        self.world: WorldInterface = world or NullWorldInterface()
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

    async def _generate_in_background(
        self,
        session_id: str,
        prompt: str,
        sender_id: str | None = None,
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
        odbiorców (SSE, WebSockets satelitów w `server.voice` itd.).

        Każde zdarzenie niesie DWA niezależne identyfikatory, celowo rozdzielone:

        * `session_id` — tożsamość sesji/pamięci. **Nigdy się nie zmienia** w trakcie
          tury; obserwatorzy sesji (`watch_session`, `interact_stream`, Web UI)
          filtrują wyłącznie po nim.
        * `target_client_id` — adres dostawy. Startuje jako `sender_id` i może się
          zmienić w trakcie tury, gdy narzędzie zwróci `ToolResult.redirect_sender_id`
          (np. `WorldEngine.speak_in_room`); odbiorcy fizyczni (gniazdo satelity w
          `server.voice`) filtrują wyłącznie po nim. Kernel mechanicznie przestawia
          adres, nie znając powodu przekierowania.

        Wcześniej obie role pełniło jedno pole `session_id`, co działało tylko dzięki
        temu, że dla satelit `session_id == sender_id`; przekierowanie na klienta, u
        którego te wartości się różnią (np. przeglądarka: sesja czatu vs `sender_id`
        z localStorage), publikowało zdarzenia pod tagiem, którego nikt nie słuchał —
        odpowiedź znikała bez błędu. Rozdzielenie usuwa też potrzebę dawnego
        dual-castu zdarzeń terminalnych (istniał wyłącznie po to, by `interact_stream`
        nie zawisł, gdy tag dostawy uciekł).
        """
        target_client_id = sender_id if sender_id is not None else session_id

        async def _publish(event_type: ServerEventType, payload_extra: dict[str, Any]) -> None:
            await self.event_bus.publish(
                Event(
                    type=event_type,
                    payload={"session_id": session_id, "target_client_id": target_client_id, **payload_extra},
                    sender="agent_engine",
                )
            )

        # 1. Rejestracja pytania użytkownika w pamięci sesji (I/O na dysku poza event loopem)
        await asyncio.to_thread(self.memory_manager.add_message, session_id=session_id, role="user", content=prompt)
        # Rozgłoszenie treści wiadomości użytkownika — jedyny sposób, w jaki obserwator
        # sesji (np. `watch_session()`, Web UI) dowiaduje się o pytaniu, gdy tura została
        # zainicjowana gdzie indziej (satelita/cron/inna karta przeglądarki): dotąd treść
        # promptu trafiała wyłącznie do pamięci, nigdy na `EventBus`.
        await _publish(ServerEventType.CHAT_USER_MESSAGE, {"content": prompt})

        self._generation_buffers[session_id] = ""

        steps: list[ToolStepPayload] = []

        try:
            # 2. Budowa kontekstu tej tury od zera przez silnik świata (WorldInterface)
            #    — nigdy cache'owana między turami. Jeśli World dostarcza `system_prompt`,
            #    jest to KOMPLETNY prompt (World jest jedynym autorem) — fallback kernela
            #    (`prompt_store`) czytany jest tylko gdy World milczy (np. NullWorldInterface).
            context_build = await self.world.build(sender_id=sender_id)
            tool_defs = context_build.tool_definitions
            dispatch_tool = context_build.dispatch
            system_prompt = context_build.system_prompt
            if system_prompt is None:
                system_prompt = await self.prompt_store.get_content()

            # 3. Pobranie aktualnej historii i zbudowanie kontekstu LLM
            history = self.memory_manager.get_history(session_id=session_id)
            working_messages = self.context_builder.build_messages(
                session_history=history,
                system_prompt=system_prompt,
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
                    await _publish(ServerEventType.CHAT_CHUNK, {"chunk": event})

                if not pending_calls:
                    break

                working_messages.append(LLMMessage(role="assistant", content=turn_text, tool_calls=pending_calls))
                for call in pending_calls:
                    step_start: ToolStepPayload = {
                        "type": "tool_call",
                        "call_id": call.id,
                        "name": call.name,
                        "text_offset": len(self._generation_buffers.get(session_id, "")),
                        "arguments": call.arguments,
                        "content": None,
                        "is_error": None,
                    }
                    steps.append(step_start)
                    await _publish(ServerEventType.TOOL_CALL_START, step_start)

                    result = await dispatch_tool(call.name, call.arguments)
                    logger.info(
                        f"Wywołano narzędzie '{call.name}' [sesja: '{session_id}']: "
                        f"{'błąd' if result.is_error else 'ok'}"
                    )
                    if result.redirect_sender_id is not None and result.redirect_sender_id != target_client_id:
                        logger.info(
                            f"Przekierowano dostawę odpowiedzi [sesja: '{session_id}'] "
                            f"z '{target_client_id}' na '{result.redirect_sender_id}'."
                        )
                        target_client_id = result.redirect_sender_id

                    step_result: ToolStepPayload = {
                        "type": "tool_result",
                        "call_id": call.id,
                        "name": call.name,
                        "text_offset": len(self._generation_buffers.get(session_id, "")),
                        "arguments": None,
                        "content": result.content,
                        "is_error": result.is_error,
                    }
                    steps.append(step_result)
                    await _publish(ServerEventType.TOOL_CALL_RESULT, step_result)

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
                metadata={"steps": steps} if steps else None,
            )

            await _publish(ServerEventType.CHAT_DONE, {})

        except asyncio.CancelledError:
            logger.info(f"Generowanie odpowiedzi dla sesji '{session_id}' zostało przerwane.")
            partial_text = self._generation_buffers.get(session_id, "")
            if partial_text.strip():
                await asyncio.to_thread(
                    self.memory_manager.add_message,
                    session_id=session_id,
                    role="assistant",
                    content=partial_text + " [Przerwano]",
                    metadata={"steps": steps} if steps else None,
                )
            await _publish(ServerEventType.CHAT_CANCELLED, {})
            raise
        except Exception as err:
            # Pełny techniczny szczegół (np. surowa treść odpowiedzi API dostawcy LLM —
            # bywa w niej wewnętrzne ID organizacji/konta, zaobserwowane na żywo w błędzie
            # 429 Groq) trafia WYŁĄCZNIE do logów (konsola + data/logs/regis.log). Treść
            # widoczna dla użytkownika (pamięć + zdarzenie CHAT_ERROR, doręczane też do
            # satelit głosowych jako komunikat kontrolny) jest świadomie ogólna.
            logger.error(f"Błąd podczas generowania odpowiedzi dla sesji '{session_id}': {err}")
            user_facing_error = "Wystąpił błąd podczas generowania odpowiedzi. Spróbuj ponownie za chwilę."
            # Utrwalamy odpowiedź błędu sparowaną z pytaniem użytkownika, by historia
            # nigdy nie zostawiała nieodpowiedzianej wiadomości użytkownika w kontekście.
            # KLUCZOWE: doklejamy komunikat błędu do JUŻ ZGROMADZONEGO bufora tekstu
            # (mirror gałęzi CancelledError wyżej), nie zastępujemy go całkowicie — kroki
            # narzędzi w `steps` mają `text_offset` liczony względem tego bufora; podmiana
            # na zupełnie inny, krótszy string powodowała przycięcie offsetu do końca tekstu
            # przy replayu z historii, przez co krok narzędzia renderował się PO komunikacie
            # błędu zamiast przed nim (kolejność odwrócona względem faktycznego przebiegu).
            partial_text = self._generation_buffers.get(session_id, "")
            error_marker = f"[Błąd generowania odpowiedzi: {user_facing_error}]"
            persisted_content = f"{partial_text}\n\n{error_marker}" if partial_text.strip() else error_marker
            await asyncio.to_thread(
                self.memory_manager.add_message,
                session_id=session_id,
                role="assistant",
                content=persisted_content,
                metadata={"is_error": True, "steps": steps} if steps else {"is_error": True},
            )
            await _publish(ServerEventType.CHAT_ERROR, {"error": user_facing_error})
            raise
        finally:
            self._active_tasks.pop(session_id, None)
            self._generation_buffers.pop(session_id, None)

    def _subscribe_session_events(
        self, session_id: str, queue: "asyncio.Queue[StreamEvent]"
    ) -> list[tuple[ServerEventType, Any]]:
        """Rejestruje w `EventBus` komplet handlerów tłumaczących zdarzenia `CHAT_*`/
        `TOOL_CALL_*` danej sesji na `StreamEvent` wrzucane do `queue` — współdzielone przez
        `interact_stream()` (subskrypcja na czas jednej tury) i `watch_session()`
        (subskrypcja pasywna, bez limitu czasu). Zwraca listę (typ, handler) do późniejszego
        `unsubscribe` przez wywołującego (finally bloku), gdy przestaje mu być potrzebna.
        """

        def _step_payload(event: Event[Any]) -> dict[str, Any]:
            # "type" wewnątrz ToolStepPayload ("tool_call"/"tool_result") jest zbędny tutaj —
            # StreamEvent.type ("tool_start"/"tool_result") już jednoznacznie opisuje rodzaj
            # zdarzenia SSE; zostawienie obu kolidowałoby przy spreadzie payloadu w routes/chat.py.
            return {k: v for k, v in event.payload.items() if k not in ("session_id", "type")}

        async def on_user_message(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(StreamEvent(type="user_message", payload={"content": event.payload.get("content", "")}))

        async def on_chunk(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(StreamEvent(type="chunk", payload={"chunk": event.payload.get("chunk", "")}))

        async def on_tool_start(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(StreamEvent(type="tool_start", payload=_step_payload(event)))

        async def on_tool_result(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(StreamEvent(type="tool_result", payload=_step_payload(event)))

        async def on_done(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(StreamEvent(type="done", payload={}))

        async def on_error(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(
                    StreamEvent(type="error", payload={"error": event.payload.get("error", "Nieznany błąd generowania.")})
                )

        async def on_cancelled(event: Event[Any]) -> None:
            if event.payload.get("session_id") == session_id:
                await queue.put(StreamEvent(type="cancelled", payload={}))

        subscriptions: list[tuple[ServerEventType, Any]] = [
            (ServerEventType.CHAT_USER_MESSAGE, on_user_message),
            (ServerEventType.CHAT_CHUNK, on_chunk),
            (ServerEventType.TOOL_CALL_START, on_tool_start),
            (ServerEventType.TOOL_CALL_RESULT, on_tool_result),
            (ServerEventType.CHAT_DONE, on_done),
            (ServerEventType.CHAT_ERROR, on_error),
            (ServerEventType.CHAT_CANCELLED, on_cancelled),
        ]
        for event_type, handler in subscriptions:
            self.event_bus.subscribe(event_type, handler)
        return subscriptions

    async def interact_stream(
        self,
        session_id: str = "session_default",
        prompt: str = "",
        sender_id: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Główna strumieniowa pętla konwersacyjna. Utrwala zapytanie i odpowiedź w pamięci sesji.

        Subskrybuje zdarzenia `EventBus` dotyczące tej konkretnej sesji na czas trwania
        strumieniowania i tłumaczy je z powrotem na strumień ustrukturyzowanych zdarzeń
        (tekst, start/wynik wywołania narzędzia) dla wywołującego. Subskrypcja jest
        po `session_id`, które nigdy się nie zmienia — nawet gdy narzędzie przekieruje
        *dostawę* na innego klienta (`ToolResult.redirect_sender_id` zmienia wyłącznie
        `target_client_id`, patrz `_generate_in_background`), ten strumień widzi całą
        turę od początku do końca.

        :param session_id: Identyfikator sesji backendowej.
        :param prompt: Nowa treść wiadomości użytkownika.
        :param sender_id: Opaque identyfikator nadawcy (np. satelity) — nieinterpretowany
            przez kernel, przekazywany dalej do `WorldInterface.build()`; służy też jako
            początkowy adres dostawy (`target_client_id`).
        :yields: Kolejne `StreamEvent` (fragmenty tekstu oraz kroki tool-callingu).
        """
        if self.is_session_busy(session_id):
            logger.warning(f"Sesja '{session_id}' jest zajęta. Odrzucono nakładające się zapytanie.")
            raise RuntimeError(f"Sesja '{session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.")

        logger.info(f"Strumieniowa interakcja [Sesja: '{session_id}']: '{prompt}'")

        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        subscriptions = self._subscribe_session_events(session_id, queue)

        bg_task = asyncio.create_task(
            self._generate_in_background(
                session_id=session_id,
                prompt=prompt,
                sender_id=sender_id,
            )
        )
        self._active_tasks[session_id] = bg_task

        try:
            while True:
                stream_event = await queue.get()
                if stream_event.type in ("user_message", "chunk", "tool_start", "tool_result"):
                    yield stream_event
                elif stream_event.type == "done":
                    break
                elif stream_event.type == "cancelled":
                    raise asyncio.CancelledError()
                elif stream_event.type == "error":
                    raise RuntimeError(stream_event.payload.get("error"))
        finally:
            for event_type, handler in subscriptions:
                self.event_bus.unsubscribe(event_type, handler)

    async def watch_session(self, session_id: str) -> AsyncIterator[StreamEvent]:
        """Pasywna, długożyjąca obserwacja `EventBus` po `session_id` — mirror stałej
        subskrypcji `VoiceConnection` po `sender_id` w `voice/gateway.py`, tyle że dla
        dowolnego klienta REST/SSE (typowo Web UI).

        W odróżnieniu od `interact_stream()` NIE odpala żadnej tury i NIE kończy się na
        `done`/`error`/`cancelled` — po prostu przekazuje każde zdarzenie dalej i wraca po
        kolejne, aż wywołujący przerwie iterację (np. klient SSE się rozłączy). Dzięki
        temu widzi KAŻDĄ turę tej sesji w czasie rzeczywistym, niezależnie od tego, kto ją
        zainicjował (Web UI, satelita, cron, inna karta przeglądarki) — bez tego tylko
        strumień zainicjowany przez to samo żądanie (`interact_stream`) widział własną
        turę na żywo, reszta dowiadywała się dopiero z przeładowania historii.

        :param session_id: Identyfikator sesji backendowej do obserwowania.
        :yields: Każde `StreamEvent` tej sesji, w kolejności wystąpienia, bez końca.
        """
        queue: asyncio.Queue[StreamEvent] = asyncio.Queue()
        subscriptions = self._subscribe_session_events(session_id, queue)
        try:
            while True:
                yield await queue.get()
        finally:
            for event_type, handler in subscriptions:
                self.event_bus.unsubscribe(event_type, handler)

    async def interact(
        self,
        session_id: str = "session_default",
        prompt: str = "",
        sender_id: str | None = None,
    ) -> ChatResponseDTO:
        """Ścisła, niestrumieniowa konwersacja bazująca bezpośrednio na strumieniowej pętli (DRY wrapper).

        :param session_id: Identyfikator sesji backendowej.
        :param prompt: Nowa treść wiadomości użytkownika.
        :param sender_id: Opaque identyfikator nadawcy (np. satelity) — nieinterpretowany przez kernel.
        :return: Struktura ChatResponseDTO z wygenerowaną odpowiedzią i nazwą modelu.
        """
        _ = [
            chunk
            async for chunk in self.interact_stream(
                session_id=session_id, prompt=prompt, sender_id=sender_id
            )
        ]

        session = self.memory_manager.get_or_create_session(session_id)
        last_message = session.messages[-1]

        return ChatResponseDTO(
            session_id=session_id,
            message=last_message,
            model=getattr(self.llm_provider, "model", None),
        )

    def start_interaction(
        self,
        session_id: str,
        prompt: str,
        sender_id: str | None = None,
    ) -> None:
        """Odpala interakcję w tle i **od razu wraca** — jednokierunkowy "wyślij i zapomnij".

        W przeciwieństwie do `interact()`/`interact_stream()` nie subskrybuje
        `EventBus` w ogóle i nie czeka na wynik — wywołujący (typowo `server.voice`,
        gdzie gniazdo satelity ma już własną, ciągłą subskrypcję `EventBus` po
        swoim `sender_id`, niezależną od tego wywołania) dowiaduje się o odpowiedzi
        wyłącznie przez zdarzenia `EventBus`, nigdy przez wartość zwracaną stąd.

        :raises RuntimeError: jeśli sesja jest już zajęta.
        """
        if self.is_session_busy(session_id):
            logger.warning(f"Sesja '{session_id}' jest zajęta. Odrzucono nakładające się zapytanie.")
            raise RuntimeError(f"Sesja '{session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie.")

        logger.info(f"Jednokierunkowa interakcja [Sesja: '{session_id}']: '{prompt}'")
        task = asyncio.create_task(
            self._generate_in_background(session_id=session_id, prompt=prompt, sender_id=sender_id)
        )
        self._active_tasks[session_id] = task
