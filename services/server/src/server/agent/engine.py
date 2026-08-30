"""Rdzeń agenta — publiczne API kernela i kompozycja jego części.

Silnik sam nie prowadzi już tury: robi to `TurnRunner` (`agent/turn.py`), księgowanie
zdarzeń należy do `agent/turn_events.py`, a „która sesja pracuje" do `agent/tasks.py`.
Tutaj zostaje to, po co wywołujący sięga: cztery sposoby odpalenia/obserwowania tury
i jeden na jej anulowanie.

Cztery wejścia, bo realnie są cztery różne oczekiwania:

```text
    interact()          -> czekam na komplet odpowiedzi        (POST /chat)
    interact_stream()   -> chcę widzieć swoją turę na żywo     (POST /chat/stream)
    start_interaction() -> odpal i zapomnij, odbiorę gdzie indziej (satelita, /chat/send)
    watch_session()     -> chcę widzieć KAŻDĄ turę tej sesji   (GET .../watch)
```
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from shared import ChatResponseDTO, EventBus, get_logger

from server.agent.context import ContextBuilder
from server.agent.context_provider import ContextBuild, NullWorldInterface, WorldInterface
from server.agent.memory import MemoryManager
from server.agent.prompts import AgentDefaultPromptStore
from server.agent.tasks import SessionTaskRegistry
from server.agent.turn import ReasoningRunPayload, ToolStepPayload, TurnRunner
from server.agent.turn_events import SessionEventSubscription, StreamEvent, TurnAddress, TurnEventPublisher
from server.ports.llm import BaseLLMProvider

logger = get_logger("regis.agent")

__all__ = ["AgentEngine", "ReasoningRunPayload", "StreamEvent", "ToolStepPayload"]

_SESSION_BUSY = "Sesja '{session_id}' przetwarza obecnie inne zapytanie. Odczekaj lub anuluj bieżące wywołanie."


class AgentEngine:
    """Rdzeń Systemu Operacyjnego Agenta AI (Agent OS Kernel)."""

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
        # Import LENIWY z powodu KIERUNKU ZALEŻNOŚCI: kernel zna sam protokół
        # (`server.ports.llm`), a `server.ai` to sąsiednia warstwa konkretów —
        # modułowy import czyniłby z niej twardą zależność kernela od jednego dostawcy.
        if llm_provider is None:
            from server.ai.llm import OllamaProvider

            llm_provider = OllamaProvider()
        self.llm_provider: BaseLLMProvider = llm_provider
        self.memory_manager: MemoryManager = memory_manager or MemoryManager()
        self.context_builder: ContextBuilder = context_builder or ContextBuilder()
        self.event_bus: EventBus = event_bus or EventBus()
        self.prompt_store: AgentDefaultPromptStore = prompt_store or AgentDefaultPromptStore()
        # Kernel nie zna żadnej konkretnej implementacji — pusty NullWorldInterface to
        # bezpieczny domyślny stan (agent działa jak zwykły chat, bez narzędzi).
        # Kompozycja konkretnego silnika świata (server.world) należy do main.py.
        self.world: WorldInterface = world or NullWorldInterface()
        self.max_tool_iterations: int = max_tool_iterations
        self._tasks = SessionTaskRegistry()

    # --------------------------------------------------------------------------
    # Stan sesji
    # --------------------------------------------------------------------------

    def is_session_busy(self, session_id: str) -> bool:
        """Czy dla podanej sesji trwa obecnie przetwarzanie w tle."""
        return self._tasks.is_busy(session_id)

    def get_generation_buffer(self, session_id: str) -> str | None:
        """Dotychczas wygenerowany tekst albo `None`, jeśli sesja nic nie generuje.

        Czytane przy dołączaniu do sesji już pracującej (`GET .../history` dokleja to
        jako wiadomość częściową), żeby karta przeglądarki nie zaczynała od pustki."""
        return self._tasks.buffer_if_busy(session_id)

    async def cancel_interaction(self, session_id: str) -> bool:
        """Anuluje aktywne generowanie dla sesji — dla wszystkich interfejsów naraz.

        :return: True jeśli zapytanie zostało anulowane, False jeśli sesja nie była zajęta.
        """
        return await self._tasks.cancel(session_id)

    async def initialize(self) -> None:
        """Inicjalizacja rdzenia agenta."""
        logger.info("Inicjalizacja Agent Engine Kernel...")
        logger.info("Agent Engine jest gotowy.")

    async def shutdown(self) -> None:
        """Bezpieczne zamknięcie rdzenia agenta."""
        logger.info("Zamykanie Agent Engine...")
        for session_id in self._tasks.active_session_ids():
            await self.cancel_interaction(session_id)

    # --------------------------------------------------------------------------
    # Odpalanie tury
    # --------------------------------------------------------------------------

    def start_interaction(
        self,
        session_id: str,
        prompt: str,
        sender_id: str | None = None,
        session_idle_ttl_seconds: float | None = None,
    ) -> None:
        """Odpala turę w tle i **od razu wraca** — jednokierunkowy „wyślij i zapomnij".

        Nie subskrybuje `EventBus` w ogóle i nie czeka na wynik: wywołujący (typowo
        `server.voice`, gdzie gniazdo satelity ma już własną, ciągłą subskrypcję po
        swoim `sender_id`) dowiaduje się o odpowiedzi wyłącznie przez zdarzenia.

        :param session_idle_ttl_seconds: Polityka wygaszania historii tej sesji po
            bezczynności (patrz `MemoryManager`). Kernel jej nie wymyśla — podaje ją
            brzeg kompozycji, który wie, jakim klientem jest wywołujący. `None`
            (domyślne) = bez wygaszania.
        :raises RuntimeError: jeśli sesja jest już zajęta.
        """
        self._reject_if_busy(session_id)
        logger.info(f"Jednokierunkowa interakcja [Sesja: '{session_id}']: '{prompt}'")
        self._touch_session(session_id, session_idle_ttl_seconds)
        self._spawn_turn(session_id, prompt, sender_id)

    async def interact_stream(
        self,
        session_id: str = "session_default",
        prompt: str = "",
        sender_id: str | None = None,
        session_idle_ttl_seconds: float | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Odpala turę i strumieniuje jej przebieg wywołującemu.

        Subskrypcja idzie po `session_id`, które nigdy się nie zmienia — nawet gdy
        narzędzie przekieruje *dostawę* na innego klienta, ten strumień widzi całą turę
        od początku do końca.

        :raises RuntimeError: jeśli sesja jest zajęta albo tura skończyła się błędem.
        """
        self._reject_if_busy(session_id)
        logger.info(f"Strumieniowa interakcja [Sesja: '{session_id}']: '{prompt}'")
        self._touch_session(session_id, session_idle_ttl_seconds)

        with SessionEventSubscription(self.event_bus, session_id) as subscription:
            self._spawn_turn(session_id, prompt, sender_id)
            while True:
                event = await subscription.queue.get()
                if event.type == "done":
                    break
                if event.type == "cancelled":
                    raise asyncio.CancelledError()
                if event.type == "error":
                    raise RuntimeError(event.payload.get("error"))
                yield event

    async def watch_session(self, session_id: str) -> AsyncIterator[StreamEvent]:
        """Pasywna, długożyjąca obserwacja sesji — mirror stałej subskrypcji gniazda
        satelity, tyle że dla dowolnego klienta REST/SSE (typowo Web UI).

        W odróżnieniu od `interact_stream()` NIE odpala tury i NIE kończy się na
        `done`/`error`/`cancelled` — przekazuje każde zdarzenie dalej i czeka na kolejne,
        aż wywołujący przerwie iterację. Dzięki temu widzi KAŻDĄ turę tej sesji, niezależnie
        od tego, kto ją zainicjował (Web UI, satelita, cron, inna karta przeglądarki).
        """
        with SessionEventSubscription(self.event_bus, session_id) as subscription:
            while True:
                yield await subscription.queue.get()

    async def interact(
        self,
        session_id: str = "session_default",
        prompt: str = "",
        sender_id: str | None = None,
        session_idle_ttl_seconds: float | None = None,
    ) -> ChatResponseDTO:
        """Niestrumieniowa konwersacja — cienki wrapper na `interact_stream()` (DRY)."""
        async for _ in self.interact_stream(
            session_id=session_id,
            prompt=prompt,
            sender_id=sender_id,
            session_idle_ttl_seconds=session_idle_ttl_seconds,
        ):
            pass

        session = self.memory_manager.get_or_create_session(session_id)
        return ChatResponseDTO(
            session_id=session_id,
            message=session.messages[-1],
            model=getattr(self.llm_provider, "model", None),
        )

    # --------------------------------------------------------------------------

    def _touch_session(self, session_id: str, idle_ttl_seconds: float | None) -> None:
        """Sięga po sesję PRZED odpaleniem tury — czyli przed dopisaniem pytania do pamięci.

        To jedyne miejsce, w którym polityka wygaszania wnoszona przez wywołującego
        trafia do pamięci; `TurnRunner` nie musi o niej wiedzieć ani jej przekazywać.
        Sam odczyt wystarcza, bo wygaszanie przeterminowanej historii dzieje się
        wewnątrz `MemoryManager.get_or_create_session()`."""
        self.memory_manager.get_or_create_session(session_id, idle_ttl_seconds=idle_ttl_seconds)

    def _reject_if_busy(self, session_id: str) -> None:
        if self._tasks.is_busy(session_id):
            logger.warning(f"Sesja '{session_id}' jest zajęta. Odrzucono nakładające się zapytanie.")
            raise RuntimeError(_SESSION_BUSY.format(session_id=session_id))

    def _spawn_turn(self, session_id: str, prompt: str, sender_id: str | None) -> None:
        """Składa `TurnRunner` z części kernela i odpala go jako zadanie w tle.

        Adres dostawy startuje jako `sender_id`; gdy go nie ma (wywołanie headless —
        skrypt, cron), używamy `session_id`, żeby zdarzenia miały dokąd trafić."""
        runner = TurnRunner(
            llm_provider=self.llm_provider,
            memory_manager=self.memory_manager,
            context_builder=self.context_builder,
            context_factory=self._build_world_context,
            fallback_prompt=self.prompt_store.get_content,
            tasks=self._tasks,
            publisher=TurnEventPublisher(
                self.event_bus,
                TurnAddress(session_id=session_id, target_client_id=sender_id or session_id),
            ),
            max_tool_iterations=self.max_tool_iterations,
        )
        task = asyncio.create_task(runner.run(prompt=prompt, sender_id=sender_id))
        self._tasks.register(session_id, task)

    async def _build_world_context(self, sender_id: str | None) -> ContextBuild:
        """Wkład silnika świata w tę turę — budowany od zera, nigdy cache'owany."""
        return await self.world.build(sender_id=sender_id)
