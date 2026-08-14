from shared import ChatMessageDTO, get_logger
from server.agent.backend import LLMMessage
from server.agent.context_provider_contract import Fact
from server.agent.plugin_contract import EntitySpec

logger = get_logger("regis.agent.context")

DEFAULT_SYSTEM_PROMPT = (
    "Jesteś inteligentnym asystentem i centralnym jądrem Regis OS Kernel.\n"
    "Odpowiadaj zwięźle, konkretnie i pomocnie w języku polskim."
)

# Neutralne, addon-agnostyczne zdanie doklejane warunkowo, gdy agent ma w danej
# interakcji dostęp do jakichkolwiek narzędzi — nigdy nie wymienia ich nazw
# ani pochodzenia (żaden addon/integracja nie jest znany na poziomie promptu).
_TOOLS_AVAILABLE_HINT = (
    "\n\nMasz dostęp do zestawu narzędzi zewnętrznych — korzystaj z nich, gdy pomogą "
    "w realizacji zadania lub odpowiedzi na pytanie."
)


def _format_capability(tool_name: str, features: frozenset[str]) -> str:
    """Formatuje pojedynczą etykietę możliwości — dopisuje cechy w obrębie
    narzędzia, gdy istnieją (wizja, sekcja 4.1: granularność cech), pomija
    nawiasy, gdy narzędzie jest wspierane w pełni (pusty zbiór cech)."""
    if not features:
        return tool_name
    return f"{tool_name}[{', '.join(sorted(features))}]"


def _format_entities_section(entities: list[EntitySpec] | None) -> str:
    """Formatuje kanał Encji generycznie — kernel zna wyłącznie kształt z Kontraktu,
    nigdy pochodzenia (domeny) encji (wizja, sekcja 1 i 3)."""
    if not entities:
        return ""
    lines = ["\n\nDostępne encje (adresuj je wyłącznie po podanym id):"]
    for entity in entities:
        features_by_tool: dict[str, set[str]] = {}
        for capability in entity.capabilities:
            features_by_tool.setdefault(capability.tool_name, set()).update(capability.features)
        capability_labels = sorted(
            _format_capability(tool_name, frozenset(features)) for tool_name, features in features_by_tool.items()
        )
        lines.append(f"- [{entity.id}] {entity.name} (możliwości: {', '.join(capability_labels) or 'brak'})")
    return "\n".join(lines)


def _format_facts_section(facts: list[Fact] | None) -> str:
    """Formatuje kanał Faktów generycznie (wizja, sekcja 3)."""
    if not facts:
        return ""
    lines = ["\n\nZnane fakty:"]
    lines.extend(f"- {fact.key}: {fact.value}" for fact in facts)
    return "\n".join(lines)


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
        system_prompt_override: str | None = None,
        tools_available: bool = False,
        entities: list[EntitySpec] | None = None,
        facts: list[Fact] | None = None,
    ) -> list[LLMMessage]:
        """Składa listę wiadomości LLMMessage na podstawie historii sesji oraz nowego zapytania.

        Historia jest przycinana do `max_history_messages` najnowszych wiadomości (jeśli ustawiono),
        aby uniknąć przekroczenia limitu kontekstu modelu w długich konwersacjach.

        :param session_history: Dotychczasowa historia wiadomości z sesji backendowej.
        :param new_prompt: Opcjonalny nowy prompt od użytkownika (jeśli nie został jeszcze dodany do historii).
        :param system_prompt_override: Opcjonalny własny system prompt nadpisujący domyślny.
        :param tools_available: Czy w tej interakcji agent ma dostęp do jakichkolwiek narzędzi
            (agregacja z Gateway) — jeśli tak, dokleja jedno neutralne zdanie
            zachęcające do ich użycia, bez wymieniania czegokolwiek konkretnego.
        :param entities: Kanał Encji zbudowany przez Gateway na tę turę (opaque ID, nazwa,
            możliwości) — formatowany generycznie, kernel nie zna żadnej domeny.
        :param facts: Kanał Faktów zebrany przez Gateway od Dostawców kontekstu na tę turę.
        :return: Lista zwalidowanych obiektów LLMMessage gotowych do wysłania do dostawcy LLM.
        """
        messages: list[LLMMessage] = []

        # 1. Dodanie wytycznych systemowych (System Prompt) + kanały Encje/Fakty (Gateway)
        system_content = system_prompt_override or self.default_system_prompt
        if tools_available:
            system_content += _TOOLS_AVAILABLE_HINT
        system_content += _format_entities_section(entities)
        system_content += _format_facts_section(facts)
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
            # Mapujemy tylko znane role LLM (user, assistant, system)
            role = msg.role if msg.role in ("user", "assistant", "system") else "user"
            messages.append(LLMMessage(role=role, content=msg.content))

        # 3. Dodanie nowego promptu jeśli nie było go jeszcze w historii
        if new_prompt and (not session_history or session_history[-1].content != new_prompt):
            messages.append(LLMMessage(role="user", content=new_prompt))

        logger.debug(f"Zbudowano kontekst LLM z {len(messages)} wiadomościami (System Prompt + historia).")
        return messages
