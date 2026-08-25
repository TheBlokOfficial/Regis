"""Singleton-router należący do `ai.llm` — jedyny obiekt LLM, jaki trzyma Kernel
(`agent/engine.py`). Nie jest konkretnym dostawcą: przy każdym wywołaniu
rozwiązuje kandydatów do obsłużenia tury przez `BackendRegistry`, więc zmiana
aktywnego dostawcy/łańcucha fallbacku (REST) działa natychmiast, bez mutowania
stanu Kernela z zewnątrz."""

from __future__ import annotations

from typing import Any, AsyncIterator

from shared import get_logger

from server.ai.llm.circuit_breaker import CircuitBreaker
from server.ai.llm.registry import BackendRegistry
from server.ai.llm.token_budget import TokenBudgetTracker, estimate_tokens
from server.ports.llm import (
    BaseLLMProvider,
    GenerationUsage,
    LLMMessage,
    ReasoningChunk,
    ToolCallRequest,
    ToolDefinition,
)

logger = get_logger("regis.ai.llm.router")


def _billable_tokens(usage: GenerationUsage | None, estimated: int) -> int:
    """Suma tokenów tury do odnotowania w budżecie TPM.

    Dostawca może podać jeden licznik bez drugiego (albo żadnego) — wtedy brakujący
    człon zastępuje estymata, zamiast liczyć zaniżoną sumę częściową."""
    if usage is None or (usage.prompt_tokens is None and usage.completion_tokens is None):
        return estimated
    return (usage.prompt_tokens if usage.prompt_tokens is not None else estimated) + (
        usage.completion_tokens or 0
    )


class LLMRouter(BaseLLMProvider):
    """Rozwiązuje kandydatów tury na nowo przy każdym wywołaniu. **Aktywny preset
    (`active_id`) jest zawsze Priorytetem 0** — próbowany jako pierwszy, zanim
    router w ogóle spojrzy na łańcuch fallbacku (`BackendRegistry.get_fallback_chain()`).
    Łańcuch dokłada wyłącznie kolejne, awaryjne poziomy; duplikat aktywnego
    presetu w łańcuchu jest odfiltrowywany, więc nie da się przez pomyłkę
    wywołać go dwa razy w tej samej turze. Pusty łańcuch = wyłącznie aktywny
    preset, zachowanie nierozróżnialne od stanu sprzed wprowadzenia fallbacku.
    Wybór aktywnego presetu (kliknięcie „Aktywuj” w UI) pozostaje jedynym
    miejscem, w którym user wskazuje punkt startowy — router nigdy sam go
    nie dobiera.

    **Zasada bezpieczeństwa przełączania**: zamiana na kolejnego kandydata jest
    dopuszczalna WYŁĄCZNIE, dopóki bieżący kandydat nie wyemitował jeszcze
    żadnego zdarzenia strumienia. Po pierwszym `yield` błąd propaguje normalnie
    — cicha zamiana w środku odpowiedzi ucinałaby lub duplikowała już dostarczony
    tekst (krytyczne dla wyjścia głosowego, gdzie fragment mógł już trafić do TTS).
    Zweryfikowane w kodzie providera (`openai_compatible.py`): błąd HTTP jest
    rzucany zaraz po nagłówkach odpowiedzi, przed pierwszą iteracją SSE — więc
    dla tej klasy błędów (w tym 429 rate-limit) to przełączenie jest zawsze
    bezpieczne.

    Cache konkretów jest per `instance_id` (nie jeden obiekt jak wcześniej) —
    z łańcuchem różni kandydaci mogą być wybierani w różnych turach.
    """

    def __init__(
        self,
        registry: BackendRegistry,
        tracker: TokenBudgetTracker | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        self._registry = registry
        self._tracker = tracker
        self._breaker = breaker
        self._provider_cache: dict[str, tuple[dict[str, Any] | None, BaseLLMProvider]] = {}

    async def _candidate_ids(self) -> list[str]:
        """Aktywny preset jest zawsze Priorytetem 0 — próbowany jako pierwszy,
        niezależnie od tego, czy w ogóle figuruje w łańcuchu fallbacku. Łańcuch
        dokłada WYŁĄCZNIE kolejne, awaryjne poziomy; duplikat aktywnego presetu
        na liście fallbacku jest bezpieczny (odfiltrowany), nie tworzy podwójnej
        próby tego samego backendu."""
        active_id = await self._registry.get_active_backend_id()
        chain = await self._registry.get_fallback_chain()
        return [active_id, *(cid for cid in chain if cid != active_id)]

    def _resolve_cached(self, instance_id: str, options: dict[str, Any] | None) -> BaseLLMProvider | None:
        cached = self._provider_cache.get(instance_id)
        if cached is not None and cached[0] == options:
            return cached[1]
        return None

    async def generate_stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str | ReasoningChunk | ToolCallRequest | GenerationUsage]:
        all_instances = await self._registry.load_all_instances()
        if not all_instances:
            raise RuntimeError("Brak jakichkolwiek zadeklarowanych instancji backendu LLM.")

        candidates = [iid for iid in await self._candidate_ids() if iid in all_instances]
        if not candidates:
            candidates = [next(iter(all_instances))]

        estimated_tokens = estimate_tokens(messages)
        last_error: Exception | None = None

        for position, instance_id in enumerate(candidates):
            if self._breaker is not None and self._breaker.is_open(instance_id):
                logger.debug(f"Pominięto backend [{instance_id}] — circuit breaker otwarty.")
                continue

            instance = all_instances[instance_id]
            tpm_limit = instance.options.get("tpm_limit")
            if (
                self._tracker is not None
                and tpm_limit is not None
                and not self._tracker.has_budget(instance_id, estimated_tokens, tpm_limit)
            ):
                logger.debug(f"Pominięto backend [{instance_id}] — brak budżetu TPM w lokalnym trackerze.")
                continue

            provider = self._resolve_cached(instance_id, instance.options)
            if provider is None:
                provider = self._registry.create_provider_instance(instance)
                self._provider_cache[instance_id] = (instance.options, provider)

            started = False
            usage: GenerationUsage | None = None
            try:
                async for event in provider.generate_stream(messages, tools=tools, **kwargs):
                    started = True
                    if isinstance(event, GenerationUsage):
                        usage = event
                    yield event
                if self._tracker is not None:
                    # Realne zużycie, gdy dostawca je podał — estymata `len/4` tylko
                    # jako awaryjny margines. Tracker bramkuje wyłącznie wstępnie
                    # (patrz `token_budget.py`), więc rozjazd nie jest krytyczny,
                    # ale bramkowanie na prawdziwych liczbach po prostu trafia lepiej.
                    self._tracker.record(instance_id, _billable_tokens(usage, estimated_tokens))
                return
            except Exception as err:
                if started:
                    # Strumień już zaczął dostarczać treść — dalsza zamiana kandydata
                    # byłaby niebezpieczna (patrz docstring klasy). Błąd propaguje.
                    raise
                last_error = err
                if self._breaker is not None:
                    self._breaker.trip_from_error(instance_id, err)
                remaining = len(candidates) - position - 1
                logger.warning(
                    f"Backend [{instance_id}] odrzucił żądanie przed pierwszym fragmentem "
                    f"odpowiedzi: {err}. Pozostało kandydatów w łańcuchu: {remaining}."
                )
                continue

        if last_error is not None:
            raise last_error
        raise RuntimeError("Wszyscy kandydaci w łańcuchu fallbacku LLM są obecnie niedostępni (circuit breaker).")
