import json
from typing import Any

# ─── Wyjątki Modułu Node ───────────────────────────────────────────────────────

class RegisCoreException(Exception):
    """Bazowy wyjątek dla wszystkich błędów w module Node."""
    pass


class LLMConnectionError(RegisCoreException):
    """Rzucany, gdy silnik nie może nawiązać połączenia z modelem LLM."""
    pass


class HomeAssistantConnectionError(RegisCoreException):
    """Rzucany, gdy klient nie może połączyć się z serwerem Home Assistanta."""
    pass


# ─── Narzędzia Pomocnicze ──────────────────────────────────────────────────────

def build_messages_from_history(system_prompt: str, history: list[dict], current_message: str = None) -> list[dict]:
    """Odbudowuje listę wiadomości na podstawie historii konwersacji do struktury zgodnej z API LLM."""
    messages = [{"role": "system", "content": system_prompt}]
    
    for turn in history:
        messages.append({"role": "user", "content": turn["user"]})
        if turn.get("assistant"):
            messages.append({"role": "assistant", "content": turn["assistant"]})
            
    if current_message:
        messages.append({"role": "user", "content": current_message})
        
    return messages
