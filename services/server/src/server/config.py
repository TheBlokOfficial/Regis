from pathlib import Path
from pydantic import BaseModel, Field
from shared import ConfigStore, get_service_root


class Settings(BaseModel):
    """Główna konfiguracja aplikacji serwera Regis."""

    app_name: str = Field(default="Regis OS", description="Nazwa aplikacji")
    version: str = Field(default="0.1.0", description="Wersja aplikacji")
    host: str = Field(default="0.0.0.0", description="Adres nasłuchiwania HTTP/WebSocket")
    port: int = Field(default=8000, description="Port serwera HTTP/WebSocket")
    debug: bool = Field(default=False, description="Tryb debugowania")
    llm_timeout: float = Field(default=30.0, description="Globalny limit czasu zapytań do LLM w sekundach")
    llm_default_max_tokens: int = Field(default=4096, description="Domyślna maksymalna liczba tokenów wyjściowych dla modeli LLM")
    max_history_messages: int = Field(default=40, description="Maksymalna liczba ostatnich wiadomości z historii sesji dołączana do kontekstu LLM")


# Automatyczne odnajdywanie korzenia usługi (services/server)
SERVICE_DIR = get_service_root(__file__)
CONFIG_PATH = SERVICE_DIR / "config" / "settings.json"

# Instancja menedżera konfiguracji serwera
config_store = ConfigStore(Settings, CONFIG_PATH)


def load_settings() -> Settings:
    """Wczytuje i zwraca zwalidowane ustawienia serwera."""
    return config_store.load()
