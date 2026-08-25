"""Jedna tura agenta: pętla ReAct, księgowanie kroków i trzy sposoby jej zakończenia.

Wydzielone z `AgentEngine._generate_in_background()` — 249 linii z pięcioma
odpowiedzialnościami i czterema domknięciami naraz. Dziś:

* `TurnRecorder` — księguje, co się w turze wydarzyło (kroki narzędzi i przebiegi
  rozumowania) w kolejności chronologicznej,
* `TurnRunner` — prowadzi pętlę i decyduje, co utrwalić przy każdym z trzech wyjść
  (odpowiedź, anulowanie, błąd).

**Kształt `metadata` jest kontraktem, nie szczegółem.** W `data/sessions/*.json`
leżą realne rozmowy użytkownika, których projekt świadomie nie migruje (patrz
`docs/manifest.md`, „Reasoning rozdzielony strukturalnie"), a Web UI odtwarza
z nich całe drzewko tury. Pola `seq`/`text_offset`/`call_id` muszą zostać takie,
jakie były.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Literal, TypedDict

from shared import TurnRef, bind_turn, get_logger, new_turn_id

from server.agent.context import ContextBuilder
from server.agent.context_provider import ContextBuild
from server.agent.memory import MemoryManager
from server.agent.tasks import SessionTaskRegistry
from server.agent.turn_events import TurnEventPublisher
from server.events import ServerEventType
from server.ports.llm import BaseLLMProvider, GenerationUsage, LLMMessage, ReasoningChunk, ToolCallRequest

logger = get_logger("regis.agent.turn")

ContextFactory = Callable[[str | None], Awaitable[ContextBuild]]
"""`WorldInterface.build` — wstrzykiwane, nie importowane: runner nie zna ani
konkretnego silnika świata, ani tego, że jakikolwiek istnieje."""

FallbackPromptProvider = Callable[[], Awaitable[str]]
"""Prompt kernela, używany WYŁĄCZNIE gdy World nie dostarczy własnego."""

USER_FACING_ERROR = "Wystąpił błąd podczas generowania odpowiedzi. Spróbuj ponownie za chwilę."
"""Treść widoczna dla użytkownika przy KAŻDYM błędzie tury.

Świadomie ogólna: surowe błędy API dostawców potrafią nieść wewnętrzne dane konta
(zaobserwowane na żywo: ID organizacji Groq w treści błędu 429), a ten sam payload
zdarzenia trafia do trzech odbiorców naraz (SSE Chat UI, `interact()`, gniazdo
satelity). Jedna sanityzacja u źródła zabezpiecza wszystkich."""


class ToolStepPayload(TypedDict):
    """Pojedynczy wpis kroku pętli ReAct w kolejności chronologicznej.

    `text_offset` to długość dotychczas zakumulowanego tekstu finalnej odpowiedzi
    assistant w momencie wystąpienia kroku — pozwala frontendowi wpleść node kroku
    między segmenty tekstu, zarówno w strumieniu live, jak i przy replayu z
    `ChatMessageDTO.metadata["steps"]`. `seq` rozstrzyga kolejność tam, gdzie sam
    offset jej nie niesie: cała sekwencja myślenie -> narzędzie -> myślenie dzieje
    się przy tym samym offsecie, dopóki model nie napisze pierwszego znaku finalnej
    odpowiedzi. Kształt płaski (pola zawsze obecne, `None` gdy nieużywane w danym
    wariancie) zamiast opcjonalnych kluczy — prostszy do konsumpcji bez rozgałęzień w JS.
    """

    type: Literal["tool_call", "tool_result"]
    seq: int
    call_id: str
    name: str
    text_offset: int
    arguments: dict[str, Any] | None
    content: str | None
    is_error: bool | None


class ReasoningRunPayload(TypedDict):
    """Jeden ciągły blok rozumowania modelu (chain of thought) w kolejności chronologicznej.

    Mirror `ToolStepPayload` co do pary pól pozycjonujących (`seq`/`text_offset`), bo
    z punktu widzenia odtwarzania tury myślenie i wywołanie narzędzia to ten sam rodzaj
    bytu: coś, co wydarzyło się w konkretnym momencie pomiędzy fragmentami finalnego
    tekstu. Trafia do `ChatMessageDTO.metadata["reasoning"]` — **nigdy** do `content`
    wiadomości, bo `content` jest odsyłany do modelu w kolejnych turach i czytany na
    głos przez TTS (patrz `ports/llm.py::ReasoningChunk`).
    """

    seq: int
    text_offset: int
    content: str


class TurnRecorder:
    """Chronologiczny zapis tego, co wydarzyło się w turze poza samym tekstem odpowiedzi."""

    def __init__(self) -> None:
        self.steps: list[ToolStepPayload] = []
        self.reasoning_runs: list[ReasoningRunPayload] = []
        self._seq = 0
        self._pending_reasoning = ""

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def append_reasoning(self, text: str) -> None:
        """Rozumowanie akumuluje się w PRZEBIEGI (jeden przebieg = jeden ciągły blok
        myślenia); domyka je `flush_reasoning()`."""
        self._pending_reasoning += text

    def flush_reasoning(self, text_offset: int) -> None:
        """Domyka bieżący przebieg rozumowania. Wołane przy pierwszym fragmencie
        odpowiedzi, przed wywołaniem narzędzia i na koniec iteracji."""
        if not self._pending_reasoning:
            return
        self.reasoning_runs.append(
            {"seq": self.next_seq(), "text_offset": text_offset, "content": self._pending_reasoning}
        )
        self._pending_reasoning = ""

    def record_tool_call(self, call: ToolCallRequest, text_offset: int) -> ToolStepPayload:
        step: ToolStepPayload = {
            "type": "tool_call",
            "seq": self.next_seq(),
            "call_id": call.id,
            "name": call.name,
            "text_offset": text_offset,
            "arguments": call.arguments,
            "content": None,
            "is_error": None,
        }
        self.steps.append(step)
        return step

    def record_tool_result(
        self, call: ToolCallRequest, text_offset: int, content: str, is_error: bool
    ) -> ToolStepPayload:
        step: ToolStepPayload = {
            "type": "tool_result",
            "seq": self.next_seq(),
            "call_id": call.id,
            "name": call.name,
            "text_offset": text_offset,
            "arguments": None,
            "content": content,
            "is_error": is_error,
        }
        self.steps.append(step)
        return step

    def build_metadata(self, extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Metadane finalnej wiadomości — klucze dokładane tylko gdy niepuste, żeby
        wiadomość bez narzędzi i bez rozumowania została po prostu bez metadanych."""
        metadata: dict[str, Any] = dict(extra or {})
        if self.steps:
            metadata["steps"] = self.steps
        if self.reasoning_runs:
            metadata["reasoning"] = self.reasoning_runs
        return metadata or None


class TurnRunner:
    """Prowadzi jedną turę od pytania użytkownika do utrwalonej odpowiedzi.

    Realizuje pełną pętlę agentyczną (ReAct): jeśli LLM zażąda wywołania narzędzia,
    wynik wraca do niego jako kolejna wiadomość i generacja jest kontynuowana, aż
    model zwróci odpowiedź finalną albo zostanie przekroczony `max_tool_iterations`.
    Do `MemoryManager` trafia **wyłącznie finalny, skumulowany tekst** — pośrednie
    wiadomości `assistant`/`tool` żyją w lokalnej liście na czas tej interakcji.

    Postęp rozgłaszany jest wyłącznie przez `EventBus`; runner nie zna ani jednego
    odbiorcy (SSE, gniazda satelit w `server.voice`).
    """

    def __init__(
        self,
        *,
        llm_provider: BaseLLMProvider,
        memory_manager: MemoryManager,
        context_builder: ContextBuilder,
        context_factory: ContextFactory,
        fallback_prompt: FallbackPromptProvider,
        tasks: SessionTaskRegistry,
        publisher: TurnEventPublisher,
        max_tool_iterations: int,
    ) -> None:
        self._llm = llm_provider
        self._memory = memory_manager
        self._context_builder = context_builder
        self._context_factory = context_factory
        self._fallback_prompt = fallback_prompt
        self._tasks = tasks
        self._publisher = publisher
        self._max_tool_iterations = max_tool_iterations
        self._recorder = TurnRecorder()

    @property
    def _session_id(self) -> str:
        return self._publisher.address.session_id

    async def run(self, prompt: str, sender_id: str | None) -> None:
        """Cienka obwoluta nadająca turze tożsamość na czas jej trwania.

        `bind_turn` nie jest częścią prowadzenia tury — jest deklaracją „to wszystko,
        co wydarzy się poniżej, należy do tej jednej tury". Kod wołany w środku
        (dostawca LLM, jego router) może dzięki temu skorelować swoją pracę z turą,
        nie dostając ani jednego dodatkowego parametru i nie będąc tu znanym z nazwy."""
        with bind_turn(
            TurnRef(turn_id=new_turn_id(), session_id=self._session_id, sender_id=sender_id)
        ):
            await self._run(prompt, sender_id)

    async def _run(self, prompt: str, sender_id: str | None) -> None:
        session_id = self._session_id
        await self._persist(role="user", content=prompt)
        # Rozgłoszenie treści pytania — jedyny sposób, w jaki obserwator sesji
        # zainicjowanej gdzie indziej (satelita/cron/inna karta) dowiaduje się, o co
        # spytano; dotąd prompt trafiał wyłącznie do pamięci, nigdy na `EventBus`.
        await self._publisher.publish(ServerEventType.CHAT_USER_MESSAGE, {"content": prompt})
        self._tasks.start_buffer(session_id)

        try:
            # Budowa kontekstu jest W BLOKU try: awaria silnika świata (np. padnięty
            # Home Assistant) ma skończyć się sanityzowanym błędem tury, nie wyjątkiem
            # wylatującym z zadania w tle, którego nikt nie łapie.
            context_build = await self._context_factory(sender_id)
            await self._run_react_loop(context_build)
            await self._persist(
                role="assistant",
                content=self._tasks.buffer(session_id),
                metadata=self._recorder.build_metadata(),
            )
            await self._publisher.publish(ServerEventType.CHAT_DONE)
        except asyncio.CancelledError:
            await self._finish_cancelled()
            # `CancelledError` propagujemy ZAWSZE — bez tego zadanie nie zostanie
            # oznaczone jako anulowane, a `cancel_interaction()` czekałoby na nie
            # w nieskończoność.
            raise
        except Exception as err:
            # Wyjątek NIE jest propagowany dalej: w tym miejscu jest już w pełni
            # obsłużony — pełny szczegół poszedł do logów, sanityzowany komunikat do
            # pamięci sesji i na `EventBus`, skąd odbierze go każdy zainteresowany
            # (`interact_stream()` zamienia go z powrotem na wyjątek dla SWOJEGO
            # wywołującego). Ponowne rzucenie zostawiało nieodebrany wyjątek w zadaniu
            # odpalonym przez `start_interaction()` — czyli przy KAŻDEJ nieudanej turze
            # satelity głosowej rósł w logach "Task exception was never retrieved",
            # opisujący błąd, który system właśnie poprawnie obsłużył.
            await self._finish_failed(err)
        finally:
            self._tasks.release(session_id)

    # --------------------------------------------------------------------------

    async def _run_react_loop(self, context_build: ContextBuild) -> None:
        session_id = self._session_id
        history = self._memory.get_history(session_id=session_id)
        # Gdy World dostarcza `system_prompt`, jest to KOMPLETNY prompt tej tury (World
        # jest jedynym autorem) — fallback kernela czytamy tylko, gdy World milczy.
        system_prompt = context_build.system_prompt
        if system_prompt is None:
            system_prompt = await self._fallback_prompt()
        working_messages = self._context_builder.build_messages(
            session_history=history,
            system_prompt=system_prompt,
            tools_available=bool(context_build.tool_definitions),
            turn_context=context_build.turn_context,
        )

        for _iteration in range(self._max_tool_iterations):
            turn_text, pending_calls = await self._stream_one_round(working_messages, context_build)
            if not pending_calls:
                return
            working_messages.append(LLMMessage(role="assistant", content=turn_text, tool_calls=pending_calls))
            for call in pending_calls:
                result_message = await self._execute_tool(call, context_build)
                working_messages.append(result_message)
        else:
            logger.warning(
                f"Przekroczono limit {self._max_tool_iterations} iteracji pętli agentycznej "
                f"dla sesji '{session_id}'. Finalizowanie z dotychczasową odpowiedzią."
            )

    async def _stream_one_round(
        self, working_messages: list[LLMMessage], context_build: ContextBuild
    ) -> tuple[str, list[ToolCallRequest]]:
        """Jedna runda strumieniowania. Bufor odpowiedzi nie dostaje ani znaku
        rozumowania — to na nim liczą się `text_offset`, on trafia do pamięci sesji
        i on wraca do modelu w kolejnych turach."""
        session_id = self._session_id
        turn_text = ""
        pending_calls: list[ToolCallRequest] = []

        async for event in self._llm.generate_stream(working_messages, tools=context_build.tool_definitions):
            if isinstance(event, ToolCallRequest):
                self._recorder.flush_reasoning(self._tasks.buffer_length(session_id))
                pending_calls.append(event)
                continue
            if isinstance(event, ReasoningChunk):
                # Rozgłaszane na żywo (Web UI pokazuje myślenie w trakcie), ale poza
                # buforem odpowiedzi — odbiorca decyduje po `kind`, co z tym zrobić.
                self._recorder.append_reasoning(event.text)
                await self._publisher.publish(
                    ServerEventType.CHAT_CHUNK, {"chunk": event.text, "kind": "reasoning"}
                )
                continue
            if isinstance(event, GenerationUsage):
                # Rozliczenie generacji nie jest treścią odpowiedzi i nie ma tu żadnego
                # konsumenta — turze jest obojętne, ile tokenów kosztowała. Gałąź MUSI
                # jednak istnieć jawnie: `else` niżej traktuje wszystko pozostałe jak
                # tekst, więc bez tego obiekt trafiłby do bufora odpowiedzi, do pamięci
                # sesji i z powrotem do modelu w kolejnej turze.
                continue
            self._recorder.flush_reasoning(self._tasks.buffer_length(session_id))
            turn_text += event
            self._tasks.append_to_buffer(session_id, event)
            await self._publisher.publish(ServerEventType.CHAT_CHUNK, {"chunk": event, "kind": "answer"})

        self._recorder.flush_reasoning(self._tasks.buffer_length(session_id))
        return turn_text, pending_calls

    async def _execute_tool(self, call: ToolCallRequest, context_build: ContextBuild) -> LLMMessage:
        session_id = self._session_id
        step_start = self._recorder.record_tool_call(call, self._tasks.buffer_length(session_id))
        await self._publisher.publish(ServerEventType.TOOL_CALL_START, step_start)

        result = await context_build.dispatch(call.name, call.arguments)
        logger.info(
            f"Wywołano narzędzie '{call.name}' [sesja: '{session_id}']: {'błąd' if result.is_error else 'ok'}"
        )
        # Kernel traktuje przekierowanie czysto mechanicznie — zmienia adres dostawy
        # na resztę tury, nie znając powodu (to wyłączna wiedza silnika świata).
        if result.redirect_sender_id is not None and result.redirect_sender_id != self._publisher.address.target_client_id:
            logger.info(
                f"Przekierowano dostawę odpowiedzi [sesja: '{session_id}'] "
                f"z '{self._publisher.address.target_client_id}' na '{result.redirect_sender_id}'."
            )
            self._publisher.address.redirect_to(result.redirect_sender_id)

        step_result = self._recorder.record_tool_result(
            call, self._tasks.buffer_length(session_id), result.content, result.is_error
        )
        await self._publisher.publish(ServerEventType.TOOL_CALL_RESULT, step_result)
        return LLMMessage(role="tool", content=result.content, tool_call_id=call.id, tool_name=call.name)

    # --------------------------------------------------------------------------
    # Trzy wyjścia z tury
    # --------------------------------------------------------------------------

    async def _finish_cancelled(self) -> None:
        session_id = self._session_id
        logger.info(f"Generowanie odpowiedzi dla sesji '{session_id}' zostało przerwane.")
        partial_text = self._tasks.buffer(session_id)
        if partial_text.strip():
            await self._persist(
                role="assistant",
                content=partial_text + " [Przerwano]",
                metadata=self._recorder.build_metadata(),
            )
        await self._publisher.publish(ServerEventType.CHAT_CANCELLED)

    async def _finish_failed(self, err: Exception) -> None:
        """Pełny techniczny szczegół trafia WYŁĄCZNIE do logów; użytkownik dostaje
        `USER_FACING_ERROR` (patrz uzasadnienie przy tej stałej).

        KLUCZOWE: komunikat błędu jest DOKLEJANY do już zgromadzonego bufora, nie
        zastępuje go. Kroki narzędzi mają `text_offset` liczony względem tego bufora;
        podmiana na krótszy string przycinała offsety do końca tekstu i przy replayu
        z historii krok narzędzia renderował się PO komunikacie błędu zamiast przed nim.
        """
        session_id = self._session_id
        logger.error(f"Błąd podczas generowania odpowiedzi dla sesji '{session_id}': {err}")
        partial_text = self._tasks.buffer(session_id)
        error_marker = f"[Błąd generowania odpowiedzi: {USER_FACING_ERROR}]"
        await self._persist(
            role="assistant",
            content=f"{partial_text}\n\n{error_marker}" if partial_text.strip() else error_marker,
            metadata=self._recorder.build_metadata({"is_error": True}),
        )
        await self._publisher.publish(ServerEventType.CHAT_ERROR, {"error": USER_FACING_ERROR})

    async def _persist(self, *, role: str, content: str, metadata: dict[str, Any] | None = None) -> None:
        """Zapis na dysk poza pętlą zdarzeń."""
        await asyncio.to_thread(
            self._memory.add_message,
            session_id=self._session_id,
            role=role,
            content=content,
            metadata=metadata,
        )
