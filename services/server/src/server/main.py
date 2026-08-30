import asyncio
from pathlib import Path

import uvicorn
from shared import EventBus, data_dir, get_logger, load_dotenv, setup_logging
from shared import __version__ as REGIS_VERSION

from server.agent import AgentEngine
from server.agent.context import ContextBuilder
from server.agent.memory import MemoryManager
from server.agent.prompts import AgentDefaultPromptStore
from server.ai.llm import BackendRegistry, CircuitBreaker, LLMRouter, TokenBudgetTracker
from server.ai.stt import STTRegistry, STTRouter
from server.ai.tts import TTSRegistry, TTSRouter
from server.ai.wakeword import OnnxWakeWordDetector, ThresholdEnergyWakeWordDetector
from server.config import Settings, config_store, load_settings
from server.discovery import DiscoveryBroadcaster
from server.network.gateway import create_gateway_app
from server.ports.wakeword import WakeWordDetector
from server.telemetry import GenerationLogStore, RecordingLLMProvider, TurnAttemptCollector
from server.voice.gateway import WakeWordDetectorFactory, create_voice_router
from server.voice.presence import ClientPresenceRegistry
from server.voice.provider_routes import create_voice_providers_router
from server.voice.routes import create_voice_status_router
from server.world import WorldEngine

# 1. Konfiguracja jednolitych, minimalistycznych logów — konsola + plik z rotacją
#    (data/logs/regis.log, gitignorowane jak reszta data/). Plik trzyma pełny techniczny
#    szczegół błędów (np. treść odpowiedzi API dostawcy LLM), których UI świadomie nie
#    pokazuje wprost użytkownikowi (patrz agent/engine.py, obsługa błędów tury).
# Wczytanie configu musi poprzedzić setup_logging — `Settings.debug` (dotąd martwe pole)
# steruje poziomem: true = DEBUG, m.in. score wake-worda przy każdym inference
# (`ai/wakeword/detectors.py::OnnxWakeWordDetector.process()`), false (domyślnie) = INFO.
# `.env` PRZED `load_settings()` — nadpisania środowiskowe (REGIS_HOST/PORT/DEBUG) oraz
# katalogi (REGIS_DATA_DIR/REGIS_CONFIG_DIR) muszą być widoczne, zanim cokolwiek policzy
# sobie ścieżkę albo wczyta konfigurację. Zmienne już obecne w środowisku mają
# pierwszeństwo przed plikiem (patrz `shared/env.py`), więc `docker compose` wygrywa.
_env_file = load_dotenv(__file__)
_startup_settings = load_settings()
setup_logging(
    level="DEBUG" if _startup_settings.debug else "INFO",
    log_file=data_dir(__file__) / "logs" / "regis.log",
)
logger = get_logger("regis.main")
if _env_file is not None:
    logger.info(f"Konfiguracja środowiskowa wczytana z [{_env_file}].")


def _resolve_wakeword_model_path(configured: str) -> Path:
    """Ścieżka do modelu `.onnx` — bezwzględna albo względna wobec katalogu danych.

    Zgodność wsteczna: dotychczasowe konfiguracje trzymają `"data/wakeword/regis.onnx"`,
    czyli ścieżkę względną wobec KORZENIA USŁUGI, bo tak ją kiedyś rozwiązywano. Odkąd
    katalog danych może leżeć gdziekolwiek (`REGIS_DATA_DIR`), punktem odniesienia jest
    on sam — wiodące `data/` jest więc obcinane. Bez tego wake-word po cichu spadłby do
    placeholdera progu amplitudy: brak pliku kończy się tu `warning`, nie błędem.
    """
    candidate = Path(configured).expanduser()
    if candidate.is_absolute():
        return candidate
    parts = candidate.parts
    if parts and parts[0] == "data":
        candidate = Path(*parts[1:])
    return data_dir(__file__) / candidate


def _build_wakeword_detector_factory(settings: Settings) -> tuple[WakeWordDetectorFactory, str]:
    """Wybiera realny detektor `.onnx` (`Settings.wakeword_model_path` ustawiony i plik
    istnieje) albo placeholder progu amplitudy — łagodna degradacja, ten sam wzorzec co
    brak konfiguracji Home Assistant w `WorldEngine`. Zwraca fabrykę (nowa instancja per
    połączenie, patrz `server/ai/wakeword/detectors.py`) i nazwę klasy do statusu `/voice/status`.

    `threshold` NIE jest zamykany w closure przy starcie procesu — `factory()` woła
    `load_settings()` na świeżo przy każdym połączeniu, więc zmiana progu przez
    `PUT /api/v1/voice/client-config` działa od razu, bez restartu serwera (ten sam
    wzorzec "instant effect" co `STTRouter`/`TTSRouter`/`LLMRouter`). `model_path`
    zostaje capture'owany raz — plik modelu `.onnx` się nie zmienia w locie."""
    if not settings.wakeword_model_path:
        return ThresholdEnergyWakeWordDetector, ThresholdEnergyWakeWordDetector.__name__

    model_path = _resolve_wakeword_model_path(settings.wakeword_model_path)
    if not model_path.exists():
        logger.warning(f"Plik modelu wake-word nie istnieje [{model_path}] — używam placeholdera progu amplitudy.")
        return ThresholdEnergyWakeWordDetector, ThresholdEnergyWakeWordDetector.__name__

    def factory() -> WakeWordDetector:
        return OnnxWakeWordDetector(model_path, load_settings().wakeword_threshold)

    return factory, OnnxWakeWordDetector.__name__


async def main() -> None:
    settings = load_settings()
    logger.info(f"Uruchamianie {settings.app_name} (v{REGIS_VERSION})...")

    # 1. Tworzenie centralnej magistrali zdarzeń (Event Bus), współdzielonej przez AgentEngine
    event_bus = EventBus()

    # 2. Inicjalizacja rejestru backendów LLM. `LLMRouter` to singleton należący do
    #    `server.ai.llm` — jedyny obiekt LLM, jaki trzyma Kernel: sam rozwiązuje aktywny
    #    backend przy każdym wywołaniu, więc zmiana aktywnego dostawcy przez
    #    `PUT /api/v1/llm/providers/active` działa natychmiast, bez mutowania
    #    `agent_engine` z zewnątrz.
    #    Dekorator `RecordingLLMProvider` opakowuje router i zapisuje zrzut każdego
    #    wywołania (zakładka „Logi"). Kernel dostaje go zamiast routera i nie zauważa
    #    różnicy — to nadal `BaseLLMProvider`. `TurnAttemptCollector` powstaje PIERWSZY,
    #    bo trafia w dwa miejsca naraz: router zgłasza mu próby łańcucha fallbacku,
    #    dekorator je odbiera (patrz `telemetry/recorder.py`).
    backend_registry = BackendRegistry()
    generation_log = GenerationLogStore(
        db_path=data_dir(__file__) / "telemetry" / "generations.db",
        retention_records=settings.telemetry_retention_records,
        max_record_bytes=settings.telemetry_max_record_bytes,
    )
    await generation_log.start()
    attempt_collector = TurnAttemptCollector()
    llm_router = LLMRouter(
        backend_registry,
        tracker=TokenBudgetTracker(),
        breaker=CircuitBreaker(),
        attempt_observer=attempt_collector.record,
    )
    recording_llm = RecordingLLMProvider(llm_router, generation_log, attempt_collector)

    # 3. Inicjalizacja fallbackowego promptu kernela (używanego tylko gdy World milczy)
    prompt_store = AgentDefaultPromptStore()
    await prompt_store.ensure_defaults()

    # 4. Inicjalizacja jedynego, konkretnego silnika świata — kernel go nie zna z góry,
    #    zna wyłącznie kształt `WorldInterface` (agent/context_provider.py). Wstrzykiwany
    #    tutaj, w kompozycji aplikacji, dokładnie jak dostawca LLM. WorldEngine zarządza
    #    własnym magazynem profili promptu (`world/prompts.py`) wewnętrznie — jest jedynym
    #    autorem tożsamości agenta, gdy podłączony.
    world_engine = WorldEngine()

    # 5. Inicjalizacja rdzenia Agenta z aktywnym dostawcą LLM, EventBus, skonfigurowanym limitem historii, fallbackowym promptem i WorldEngine
    context_builder = ContextBuilder(max_history_messages=settings.max_history_messages)
    # Sufit utrwalanych wiadomości należy do kompozycji, nie do kernela: `MemoryManager`
    # zna regułę, ale nie wie, skąd wziąć jej wartość. Wygaszanie po bezczynności
    # wnosi osobno `voice/gateway.py` — per sesja, bo dotyczy tylko satelit.
    memory_manager = MemoryManager(max_persisted_messages=settings.max_persisted_messages)
    agent_engine = AgentEngine(
        llm_provider=recording_llm,
        memory_manager=memory_manager,
        context_builder=context_builder,
        event_bus=event_bus,
        prompt_store=prompt_store,
        world=world_engine,
        max_tool_iterations=settings.max_tool_iterations,
    )
    await agent_engine.initialize()
    # Tury, które skończyły się PRZED wywołaniem modelu (padnięty silnik świata przy
    # budowie kontekstu, natychmiastowe anulowanie), nie zostawiają po sobie żadnego
    # żądania — dekorator dowiaduje się o nich wyłącznie ze zdarzeń zakończenia tury.
    recording_llm.subscribe(event_bus)

    # 6. Inicjalizacja gatewaya głosowego (server.voice) — rozłącznego z WorldEngine,
    #    zna wyłącznie AgentEngine. `STTRouter`/`TTSRouter` (`server.ai.stt`/`server.ai.tts`)
    #    to singletony analogiczne do `LLMRouter` — rozwiązują aktualnie aktywną instancję
    #    przez `STTRegistry`/`TTSRegistry` (pełny CRUD wielu nazwanych instancji, mirror
    #    `BackendRegistry`, przygotowany pod przyszłe lokalne backendy STT/TTS), więc zmiana
    #    aktywnego dostawcy/configu działa od razu, bez restartu. Wake-word: realny model
    #    .onnx (Settings.wakeword_model_path), z łagodną degradacją do placeholdera progu
    #    amplitudy gdy nieskonfigurowany/brak pliku.
    # Kto jest podłączony, w jakim jest stanie i co zadeklarował w handshake —
    # mechaniczny fakt wypełniany przez gateway.py, czytany przez routes.py (panel
    # Nadawcy i dashboard Klienci w Web UI), bez importu między world/voice
    # (patrz docs/manifest.md, sekcja 5). Jeden obiekt zamiast trzech gołych kolekcji
    # wędrujących przez sygnatury dwóch fabryk routerów.
    presence = ClientPresenceRegistry()

    async def is_registered(sender_id: str) -> bool:
        """Jedyne miejsce, w którym "kto jest zatwierdzonym klientem" jest wiązane z
        konkretną implementacją. Wstrzykiwane w obie bramki wejściowe (WS i REST) tym
        samym wzorcem co `connected_sender_ids` — dzięki temu ani `voice/`, ani
        `network/routes/` nie importują `world/`, a mimo to obaj klienci przechodzą
        przez tę samą, jedną bramkę rejestracji."""
        senders = await world_engine.get_senders()
        return sender_id in senders.entries

    stt_registry = STTRegistry()
    tts_registry = TTSRegistry()
    voice_stt_provider = STTRouter(stt_registry)
    voice_tts_provider = TTSRouter(tts_registry)
    wakeword_detector_factory, wakeword_detector_class_name = _build_wakeword_detector_factory(settings)
    voice_router = create_voice_router(
        agent_engine=agent_engine,
        wakeword_detector_factory=wakeword_detector_factory,
        stt_provider=voice_stt_provider,
        tts_provider=voice_tts_provider,
        presence=presence,
        settings_loader=load_settings,
        is_registered=is_registered,
    )
    voice_status_router = create_voice_status_router(
        stt_provider=voice_stt_provider,
        tts_provider=voice_tts_provider,
        wakeword_detector_class_name=wakeword_detector_class_name,
        # Detektor powstaje per połączenie, więc o placeholderowość pytamy jedną świeżą
        # instancję tutaj — wybór modelu vs. progu amplitudy zapada raz, przy starcie.
        wakeword_is_placeholder=wakeword_detector_factory().is_placeholder,
        presence=presence,
        config_store=config_store,
        event_bus=event_bus,
    )
    voice_providers_router = create_voice_providers_router(stt_registry=stt_registry, tts_registry=tts_registry)

    # 7. Inicjalizacja bramki sieciowej z rejestrem backendów, magazynem promptów i tą samą
    #    instancją WorldEngine — konfiguracja przez REST jest od razu widoczna dla agenta,
    #    bo `WorldEngine.build()` czyta stan na bieżąco, co turę.
    app = create_gateway_app(
        agent_engine=agent_engine,
        backend_registry=backend_registry,
        prompt_store=prompt_store,
        world_engine=world_engine,
        voice_router=voice_router,
        voice_status_router=voice_status_router,
        voice_providers_router=voice_providers_router,
        is_registered=is_registered,
        generation_log=generation_log,
    )

    # 8. Start serwera uvicorn
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
    )

    server = uvicorn.Server(config)

    # 9. Rozgłaszanie obecności serwera w sieci lokalnej (UDP broadcast) — pozwala
    #    satelitom (services/desktop_satellite) znaleźć adres serwera bez ręcznej
    #    konfiguracji IP.
    discovery_broadcaster = DiscoveryBroadcaster(port=settings.port)
    discovery_broadcaster.start()

    logger.info(f"Bramka sieciowa gotowa na http://{settings.host}:{settings.port}")
    try:
        await server.serve()
    finally:
        discovery_broadcaster.stop()
        await agent_engine.shutdown()
        # Po `shutdown()` agenta: wpisy z ostatniej tury przed zamknięciem to często
        # dokładnie te, których się potem szuka — writer domyka kolejkę, nie porzuca jej.
        await generation_log.stop()


if __name__ == "__main__":
    asyncio.run(main())
