from shared import ChatMessageDTO, get_logger
from server.agent.backend import LLMMessage

logger = get_logger("regis.agent.context")

DEFAULT_SYSTEM_PROMPT = (
    "Jesteś inteligentnym asystentem i centralnym jądrem Regis OS Kernel.\n"
    "Obecnie Twoimi głównymi modułami są: interfejs konwersacyjny, pamięć sesyjna oraz zarządzenie dostawcami modeli LLM.\n"
    "Nie posiadasz jeszcze podłączonych wykonawczych narzędzi zewnętrznych (tool calls). "
    "Jeśli użytkownik pyta o dostępne narzędzia lub funkcje, poinformuj go zgodnie z prawdą, że moduł wywoływania funkcji (Tool Calling) jest w przygotowaniu.\n"
    "Odpowiadaj zwięźle, konkretnie i pomocnie w języku polskim."
)


class ContextBuilder:
    """Podsystem budowania i formatowania kontekstu promptu dla modeli LLM."""

    def __init__(self, default_system_prompt: str | None = None) -> None:
        self.default_system_prompt: str = default_system_prompt or DEFAULT_SYSTEM_PROMPT

    def build_messages(
        self,
        session_history: list[ChatMessageDTO],
        new_prompt: str | None = None,
        system_prompt_override: str | None = None,
    ) -> list[LLMMessage]:
        """Składa listę wiadomości LLMMessage na podstawie historii sesji oraz nowego zapytania.

        :param session_history: Dotychczasowa historia wiadomości z sesji backendowej.
        :param new_prompt: Opcjonalny nowy prompt od użytkownika (jeśli nie został jeszcze dodany do historii).
        :param system_prompt_override: Opcjonalny własny system prompt nadpisujący domyślny.
        :return: Lista zwalidowanych obiektów LLMMessage gotowych do wysłania do dostawcy LLM.
        """
        messages: list[LLMMessage] = []

        # 1. Dodanie wytycznych systemowych (System Prompt)
        system_content = system_prompt_override or self.default_system_prompt
        messages.append(LLMMessage(role="system", content=system_content))

        # 2. Mapowanie historii wiadomości z backendu do formatu dostawcy LLM
        for msg in session_history:
            # Mapujemy tylko znane role LLM (user, assistant, system)
            role = msg.role if msg.role in ("user", "assistant", "system") else "user"
            messages.append(LLMMessage(role=role, content=msg.content))

        # 3. Dodanie nowego promptu jeśli nie było go jeszcze w historii
        if new_prompt and (not session_history or session_history[-1].content != new_prompt):
            messages.append(LLMMessage(role="user", content=new_prompt))

        logger.debug(f"Zbudowano kontekst LLM z {len(messages)} wiadomościami (System Prompt + historia).")
        return messages
