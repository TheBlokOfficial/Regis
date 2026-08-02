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
    """Odbudowuje listę wiadomości na podstawie historii konwersacji do struktury zgodnej z API LLM."""
    messages = [{"role": "system", "content": system_prompt}]
    
    for turn in history:
        messages.append({"role": "user", "content": turn.get("user", "")})
        if turn.get("assistant"):
            messages.append({"role": "assistant", "content": turn.get("assistant", "")})
            
    if current_message:
        messages.append({"role": "user", "content": current_message})
        
    return messages
