from pydantic import BaseModel, Field
from shared import ConfigStore, config_dir, env_bool, env_int, env_str, get_logger

logger = get_logger("regis.config")


class Settings(BaseModel):
    """Główna konfiguracja aplikacji serwera Regis.

    **Nie ma tu pola `version`** — wersja produktu jest wyprowadzana ze stałej
    `shared.__version__` (`packages/shared/src/shared/version.py`) i nie należy do
    rzeczy, które użytkownik edytuje w pliku konfiguracyjnym. Wcześniejsze pole
    `version` żyło własnym życiem obok czterech innych kopii tego samego numeru.
    """

    app_name: str = Field(default="Regis", description="Nazwa aplikacji")
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
    satellite_session_idle_ttl_seconds: float = Field(
        default=300.0,
        description="Po ilu sekundach ciszy historia rozmowy z satelitą jest czyszczona (0 = nigdy). "
        "Satelita używa jednego session_id (równego swojemu sender_id) przez cały czas istnienia, "
        "więc bez tego limitu model dostaje wiadomości sprzed wielu godzin jako bieżącą rozmowę. "
        "Dotyczy WYŁĄCZNIE klientów głosowych — czat Web UI ma własną listę sesji i nie wygasa "
        "(politykę wnosi voice/gateway.py, kernel jej nie zna).",
    )
    max_persisted_messages: int = Field(
        default=200,
        description="Sufit liczby wiadomości utrwalanych w pliku jednej sesji (0 = bez limitu). "
        "Przycinane są najstarsze, nieodwracalnie — także w historii widocznej w Web UI. "
        "Niezależne od max_history_messages, które przycina tylko to, co idzie do modelu.",
    )
    telemetry_retention_records: int = Field(
        default=2000,
        description="Ile najnowszych zrzutów wywołań LLM trzyma zakładka Logi (data/telemetry/generations.db). Rotacja usuwa nadmiar leniwie, co kilkadziesiąt zapisów.",
    )
    telemetry_max_record_bytes: int = Field(
        default=262144,
        description="Sufit rozmiaru zrzutu kontekstu w jednym wpisie telemetrii. Po przekroczeniu ucinane są treści wiadomości (struktura zostaje), a wpis dostaje flagę `truncated`.",
    )
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
        description="Próg amplitudy PCM16 poniżej którego ramka liczy się jako cisza dla VAD "
        "satelity (patrz vad_silence_duration_ms). Ten sam próg sprawdzany jest też serwerowo "
        "w VoiceSession.handle_utterance_end() — nagranie, którego szczytowa amplituda nigdy go "
        "nie przekroczyła, jest odrzucane przed wysłaniem do STT (ochrona przed halucynacjami "
        "Whisper/Groq na czystej ciszy/szumie).",
    )


# Katalog konfiguracji: `$REGIS_CONFIG_DIR`, w przeciwnym razie `services/server/config`
# (patrz `shared/paths.py` — w kontenerze i w bundlu PyInstallera korzeń usługi nie istnieje).
CONFIG_PATH = config_dir(__file__) / "settings.json"

# Instancja menedżera konfiguracji serwera
config_store = ConfigStore(Settings, CONFIG_PATH)

HOST_VARIABLE = "REGIS_HOST"
PORT_VARIABLE = "REGIS_PORT"
DEBUG_VARIABLE = "REGIS_DEBUG"


def load_settings() -> Settings:
    """Wczytuje ustawienia z pliku i nakłada wąski zestaw nadpisań ze środowiska.

    **Nadpisywane są wyłącznie pola wdrożeniowe** — `host`, `port`, `debug`. To nie jest
    arbitralne ograniczenie, tylko warunek poprawności: `PUT /api/v1/voice/client-config`
    (`voice/routes.py`) czyta ustawienia, podmienia kilka pól i **zapisuje całość
    z powrotem do pliku**. Gdyby overlay obejmował pole edytowalne z Web UI, pierwszy
    zapis z przeglądarki zabetonowałby w JSON-ie wartość pochodzącą ze środowiska —
    cicho i nieodwracalnie.

    Zbiór nadpisywany tutaj (`host`/`port`/`debug`) i zbiór zapisywany przez Web UI
    (`wakeword_threshold`, `vad_*`) **muszą pozostać rozłączne**. Dokładając nowe
    nadpisanie, sprawdź najpierw, czy tamten endpoint go nie zapisuje.
    """
    settings = config_store.load()
    overrides: dict[str, object] = {}
    for field_name, value in (
        ("host", env_str(HOST_VARIABLE)),
        ("port", env_int(PORT_VARIABLE)),
        ("debug", env_bool(DEBUG_VARIABLE)),
    ):
        if value is not None:
            overrides[field_name] = value
    if not overrides:
        return settings
    logger.debug(f"Nadpisania ze środowiska: {overrides}")
    return settings.model_copy(update=overrides)
