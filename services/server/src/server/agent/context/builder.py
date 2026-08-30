from typing import cast

from shared import ChatMessageDTO, get_logger

from server.ports.llm import LLMMessage, LLMRole

logger = get_logger("regis.agent.context")

DEFAULT_SYSTEM_PROMPT = (
    "Jesteś Regis — inteligentnym asystentem i centralnym jądrem systemu.\n"
    "Odpowiadaj zwięźle, konkretnie i pomocnie w języku polskim.\n\n"
    "Poniższy dynamiczny kontekst (jeśli obecny) pochodzi z niezależnego, "
    "konkretnego silnika świata — nie zakładaj między jego fragmentami "
    "ukrytych zależności poza tym, co jawnie napisano."
)

# Neutralne, domenowo-agnostyczne zdanie doklejane warunkowo, gdy agent ma w danej
# interakcji dostęp do jakichkolwiek narzędzi — nigdy nie wymienia ich nazw
# ani pochodzenia (żaden konkretny silnik nie jest znany na poziomie promptu).
_TOOLS_AVAILABLE_HINT = (
    "\n\nMasz dostęp do zestawu narzędzi zewnętrznych — korzystaj z nich, gdy pomogą "
    "w realizacji zadania lub odpowiedzi na pytanie."
)


class ContextBuilder:
    """Podsystem budowania i formatowania kontekstu promptu dla modeli LLM."""

    def __init__(
        self,
        default_system_prompt: str | None = None,
        max_history_messages: int | None = 40,
    ) -> None:
        self.default_system_prompt: str = default_system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_history_messages: int | None = max_history_messages

    def build_messages(
        self,
        session_history: list[ChatMessageDTO],
        new_prompt: str | None = None,
        system_prompt: str | None = None,
        tools_available: bool = False,
        turn_context: str | None = None,
    ) -> list[LLMMessage]:
        """Składa listę wiadomości LLMMessage na podstawie historii sesji oraz nowego zapytania.

        Układ docelowy:

        ```text
        [0]      system   — tożsamość + zasady (stabilne między turami)
        [1..N-1] historia
        [N]      system   — fakty tej tury (`turn_context`)
        [N+1]    user     — pytanie użytkownika
        ```

        Historia jest przycinana do `max_history_messages` najnowszych wiadomości (jeśli ustawiono),
        aby uniknąć przekroczenia limitu kontekstu modelu w długich konwersacjach.

        :param session_history: Dotychczasowa historia wiadomości z sesji backendowej.
        :param new_prompt: Opcjonalny nowy prompt od użytkownika (jeśli nie został jeszcze dodany do historii).
        :param system_prompt: Stabilna część promptu tej tury (zwykle
            `ContextBuild.system_prompt` z implementacji `WorldInterface`, jeśli World
            jest podłączony i ma coś do powiedzenia) — wklejany bez modyfikacji.
            `None` oznacza brak wkładu World — użyty zostaje `self.default_system_prompt`
            (prosty fallback kernela, patrz `agent/prompts/`).
        :param tools_available: Czy w tej interakcji agent ma dostęp do jakichkolwiek narzędzi
            (z `ContextBuild.tool_definitions`) — jeśli tak, dokleja jedno neutralne zdanie
            zachęcające do ich użycia, bez wymieniania czegokolwiek konkretnego.
            Doklejane do wiadomości ZEROWEJ, bo jest stabilne w obrębie sesji.
        :param turn_context: Fakty prawdziwe tylko w tej turze (`ContextBuild.turn_context`)
            — wstawiane jako osobna wiadomość `system` tuż przed ostatnią wiadomością
            użytkownika. Rola `system` w środku rozmowy zweryfikowana empirycznie na
            `openai/gpt-oss-120b` (model wprost cytuje ten blok w swoim rozumowaniu);
            gdyby przyszły model ją ignorował, alternatywą jest rola `user` z markerem.
        :return: Lista zwalidowanych obiektów LLMMessage gotowych do wysłania do dostawcy LLM.
        """
        messages: list[LLMMessage] = []

        # 1. Dodanie wytycznych systemowych (System Prompt) — albo kompletny wkład World,
        #    albo domyślny fallback kernela. Nigdy sklejanie dwóch niepowiązanych autorów.
        system_content = system_prompt if system_prompt is not None else self.default_system_prompt
        if tools_available:
            system_content += _TOOLS_AVAILABLE_HINT
        messages.append(LLMMessage(role="system", content=system_content))

        # 2. Przycięcie historii do najnowszych N wiadomości i zmapowanie do formatu dostawcy LLM
        trimmed_history = session_history
        if self.max_history_messages is not None and len(session_history) > self.max_history_messages:
            trimmed_history = session_history[-self.max_history_messages:]
            logger.debug(
                f"Przycięto historię z {len(session_history)} do {len(trimmed_history)} "
                f"najnowszych wiadomości (limit: {self.max_history_messages})."
            )

        for msg in trimmed_history:
            # Mapujemy tylko znane role LLM (user, assistant, system). `ChatMessageDTO.role`
            # to zwykły `str`, więc zawężenie do `Literal` musi być jawne — inaczej dowolna
            # przyszła rola z pamięci sesji przeszłaby do dostawcy LLM bez ostrzeżenia.
            role: LLMRole = cast(LLMRole, msg.role) if msg.role in ("user", "assistant", "system") else "user"
            messages.append(LLMMessage(role=role, content=msg.content))

        # 3. Dodanie nowego promptu jeśli nie było go jeszcze w historii
        if new_prompt and (not session_history or session_history[-1].content != new_prompt):
            messages.append(LLMMessage(role="user", content=new_prompt))

        # 4. Fakty tej tury — TUŻ PRZED ostatnią wiadomością, nie na końcu listy.
        #    Ostatnia wiadomość to pytanie użytkownika (w normalnej ścieżce jest już
        #    w historii, bo `AgentEngine` zapisuje je do pamięci przed budową kontekstu;
        #    w ścieżce z `new_prompt` została właśnie dopisana wyżej). Dzięki wstawieniu
        #    przed nią model czyta: fakty -> pytanie, a nie pytanie -> fakty.
        #    Gdy nie ma żadnej wiadomości poza systemową, fakty po prostu lądują na końcu.
        if turn_context:
            insert_at = len(messages) - 1 if len(messages) > 1 else len(messages)
            messages.insert(insert_at, LLMMessage(role="system", content=turn_context))

        logger.debug(
            f"Zbudowano kontekst LLM z {len(messages)} wiadomościami "
            f"(System Prompt + historia{' + fakty tury' if turn_context else ''})."
        )
        return messages
