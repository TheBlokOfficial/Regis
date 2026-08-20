import asyncio

import uvicorn
from shared import EventBus, get_logger, get_service_root, setup_logging

from server.agent import AgentEngine
from server.agent.backend import BackendRegistry
from server.agent.context import ContextBuilder
from server.agent.prompts import AgentDefaultPromptStore
from server.config import Settings, load_settings
from server.discovery import DiscoveryBroadcaster
from server.network.gateway import create_gateway_app
from server.voice.config import VoiceProvidersConfig, load_voice_providers_config
from server.voice.gateway import WakeWordDetectorFactory, create_voice_router
from server.voice.routes import create_voice_status_router
from server.voice.stt import BaseSTTProvider, GroqSTTProvider, MockSTTProvider
from server.voice.tts import BaseTTSProvider, ElevenLabsTTSProvider, MockTTSProvider
from server.voice.wakeword import OnnxWakeWordDetector, ThresholdEnergyWakeWordDetector, WakeWordDetector
from server.world import WorldEngine

# 1. Konfiguracja jednolitych, minimalistycznych logów
setup_logging(level="INFO")
logger = get_logger("regis.main")


def _build_wakeword_detector_factory(settings: Settings) -> tuple[WakeWordDetectorFactory, str]:
    """Wybiera realny detektor `.onnx` (`Settings.wakeword_model_path` ustawiony i plik
    istnieje) albo placeholder progu amplitudy — łagodna degradacja, ten sam wzorzec co
    brak konfiguracji Home Assistant w `WorldEngine`. Zwraca fabrykę (nowa instancja per
    połączenie, patrz `server/voice/wakeword.py`) i nazwę klasy do statusu `/voice/status`."""
    if not settings.wakeword_model_path:
        return ThresholdEnergyWakeWordDetector, ThresholdEnergyWakeWordDetector.__name__

    model_path = get_service_root(__file__) / settings.wakeword_model_path
    if not model_path.exists():
        logger.warning(f"Plik modelu wake-word nie istnieje [{model_path}] — używam placeholdera progu amplitudy.")
        return ThresholdEnergyWakeWordDetector, ThresholdEnergyWakeWordDetector.__name__

    threshold = settings.wakeword_threshold

    def factory() -> WakeWordDetector:
        return OnnxWakeWordDetector(model_path, threshold)

    return factory, OnnxWakeWordDetector.__name__


def _build_stt_provider(config: VoiceProvidersConfig) -> BaseSTTProvider:
    """Pusty `groq_api_key` -> `MockSTTProvider` (łagodna degradacja, ten sam wzorzec
    co wake-word/Home Assistant)."""
    if not config.groq_api_key:
        return MockSTTProvider()
    return GroqSTTProvider(api_key=config.groq_api_key, model=config.groq_stt_model)


def _build_tts_provider(config: VoiceProvidersConfig) -> BaseTTSProvider:
    """Pusty `elevenlabs_api_key` -> `MockTTSProvider` (łagodna degradacja, ten sam
    wzorzec co wake-word/Home Assistant)."""
    if not config.elevenlabs_api_key:
        return MockTTSProvider()
    return ElevenLabsTTSProvider(
        api_key=config.elevenlabs_api_key,
        voice_id=config.elevenlabs_voice_id,
        model_id=config.elevenlabs_model_id,
    )


async def main() -> None:
    settings = load_settings()
    logger.info(f"Uruchamianie {settings.app_name} (v{settings.version})...")

    # 1. Tworzenie centralnej magistrali zdarzeń (Event Bus), współdzielonej przez AgentEngine
    event_bus = EventBus()

    # 2. Inicjalizacja rejestru backendów i pobranie aktywnego dostawcy LLM
    backend_registry = BackendRegistry()
    active_llm_provider = await backend_registry.get_active_provider()

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
    agent_engine = AgentEngine(
        llm_provider=active_llm_provider,
        context_builder=context_builder,
        event_bus=event_bus,
        prompt_store=prompt_store,
        world=world_engine,
        max_tool_iterations=settings.max_tool_iterations,
    )
    await agent_engine.initialize()

    # 6. Inicjalizacja gatewaya głosowego (server.voice) — rozłącznego z WorldEngine,
    #    zna wyłącznie AgentEngine. STT/TTS: Groq/ElevenLabs gdy skonfigurowane
    #    (VoiceProvidersConfig, edytowalne w Web UI -> Głos), łagodna degradacja do
    #    dev-providerów (Mock) gdy klucze puste. Wake-word: realny model .onnx
    #    (Settings.wakeword_model_path), z łagodną degradacją do placeholdera progu
    #    amplitudy gdy nieskonfigurowany/brak pliku.
    voice_providers_config = await load_voice_providers_config()
    voice_stt_provider = _build_stt_provider(voice_providers_config)
    voice_tts_provider = _build_tts_provider(voice_providers_config)
    wakeword_detector_factory, wakeword_detector_class_name = _build_wakeword_detector_factory(settings)
    voice_router = create_voice_router(
        agent_engine=agent_engine,
        wakeword_detector_factory=wakeword_detector_factory,
        stt_provider=voice_stt_provider,
        tts_provider=voice_tts_provider,
    )
    voice_status_router = create_voice_status_router(
        stt_provider=voice_stt_provider,
        tts_provider=voice_tts_provider,
        wakeword_detector_class_name=wakeword_detector_class_name,
    )

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


if __name__ == "__main__":
    asyncio.run(main())
