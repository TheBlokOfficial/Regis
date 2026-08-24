from pydantic import BaseModel, Field
from shared import ConfigStore, get_service_root


class Settings(BaseModel):
    """Główna konfiguracja aplikacji serwera Regis."""

    app_name: str = Field(default="Regis", description="Nazwa aplikacji")
    version: str = Field(default="0.1.0", description="Wersja aplikacji")
    host: str = Field(default="0.0.0.0", description="Adres nasłuchiwania HTTP/WebSocket")
    port: int = Field(default=8000, description="Port serwera HTTP/WebSocket")
    debug: bool = Field(
        default=False,
        description="Podnosi poziom logowania konsoli/pliku do DEBUG (np. score wake-worda przy każdym inference, patrz ai/wakeword/detectors.py). Domyślnie INFO.",
    )
    llm_timeout: float = Field(default=30.0, description="Globalny limit czasu zapytań do LLM w sekundach")
    llm_default_max_tokens: int = Field(default=4096, description="Domyślna maksymalna liczba tokenów wyjściowych dla modeli LLM")
    max_history_messages: int = Field(default=40, description="Maksymalna liczba ostatnich wiadomości z historii sesji dołączana do kontekstu LLM")
    max_tool_iterations: int = Field(default=8, description="Maksymalna liczba rund wywołań narzędzi w jednej pętli agentycznej, zanim agent zakończy z tym co wygenerował")
    wakeword_model_path: str = Field(
        default="", description="Ścieżka do wytrenowanego modelu wake-word .onnx. Puste = placeholder progu amplitudy."
    )
    wakeword_threshold: float = Field(default=0.65, description="Próg pewności detekcji wake-word (0-1)")
    vad_silence_duration_ms: float = Field(
        default=1500.0,
        description="Czas ciągłej ciszy (ms) po którym VAD satelity uznaje wypowiedź za zakończoną. Algorytm wykonuje się lokalnie na satelicie (zero rundtripu), ale ten próg jest centralnie skonfigurowany tutaj i wysyłany satelicie przy handshake (CLIENT_CONFIG).",
    )
    vad_amplitude_threshold: int = Field(
        default=500,
        description="Próg amplitudy PCM16 poniżej którego ramka liczy się jako cisza dla VAD satelity (patrz vad_silence_duration_ms).",
    )


# Automatyczne odnajdywanie korzenia usługi (services/server)
SERVICE_DIR = get_service_root(__file__)
CONFIG_PATH = SERVICE_DIR / "config" / "settings.json"

# Instancja menedżera konfiguracji serwera
config_store = ConfigStore(Settings, CONFIG_PATH)


def load_settings() -> Settings:
    """Wczytuje i zwraca zwalidowane ustawienia serwera."""
    return config_store.load()
