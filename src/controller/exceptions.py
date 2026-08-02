class RegisCoreException(Exception):
    """Bazowy wyjątek dla wszystkich błędów w Regis-Core."""
    pass

class LLMConnectionError(RegisCoreException):
    """Rzucany, gdy silnik nie może nawiązać połączenia z modelem."""
    pass

class HomeAssistantConnectionError(RegisCoreException):
    """Rzucany, gdy klient nie może połączyć się z serwerem Home Assistanta."""
    pass
