# ─── Wyjątki Aplikacji Klienckiej ──────────────────────────────────────────────

class RegisClientException(Exception):
    """Bazowy wyjątek dla wszystkich błędów w Aplikacji Klienckiej."""
    pass


class LLMConnectionError(RegisClientException):
    """Rzucany, gdy silnik nie może nawiązać połączenia z lokalnym silnikiem LLM."""
    pass

# Alias dla wstecznej kompatybilności
RegisCoreException = RegisClientException


# ─── Narzędzia Pomocnicze ──────────────────────────────────────────────────────

def build_messages_from_history(system_prompt: str, history: list[dict], current_message: str = None) -> list[dict]:
    """
    Odbudowuje listę wiadomości na podstawie historii konwersacji do struktury zgodnej z API LLM.
    Wspiera zarówno płaską listę wiadomości z rolami (standard LLM), jak i wstecznie format par tur.
    """
    messages = [{"role": "system", "content": system_prompt}]
    
    for item in history:
        if "role" in item:
            messages.append(item)
        else:
            if "user" in item:
                messages.append({"role": "user", "content": item["user"]})
            if item.get("assistant"):
                messages.append({"role": "assistant", "content": item["assistant"]})
            
    if current_message:
        messages.append({"role": "user", "content": current_message})
        
    return messages
