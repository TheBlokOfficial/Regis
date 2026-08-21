from shared import get_logger, ProviderMetadataResponse, ProviderTypeSpecDTO, ProviderOptionSpec
from server.ai.tts.models import TTSInstanceConfig, TTSProviderType
from server.ai.tts.providers import ElevenLabsTTSProvider, MockTTSProvider
from server.voice.tts import BaseTTSProvider

logger = get_logger("regis.ai.tts.factory")


class TTSFactory:
    """Fabryka do tworzenia instancji dostawców TTS z obiektów konfiguracji.
    Mirror `ai.llm.factory.LLMFactory`."""

    @staticmethod
    def create_provider(config: TTSInstanceConfig) -> BaseTTSProvider:
        logger.info(f"Tworzenie instancji dostawcy TTS '{config.name}' [ID: {config.id}, Typ: {config.type.value}]...")

        if config.type == TTSProviderType.ELEVENLABS:
            api_key = config.options.get("api_key", "")
            if not api_key:
                # Pusty klucz -> łagodna degradacja do dev-providera (ten sam wzorzec co
                # dawny `main.py::_build_tts_provider`, teraz per-instancja).
                return MockTTSProvider()
            return ElevenLabsTTSProvider(
                api_key=api_key,
                voice_id=config.options.get("voice_id", "pNInz6obpgDQGcFmaJgB"),
                model_id=config.options.get("model_id", "eleven_multilingual_v2"),
            )
        else:
            raise ValueError(f"Nieobsługiwany typ dostawcy TTS: {config.type}")

    @staticmethod
    def get_all_schemas() -> ProviderMetadataResponse:
        """Jedyne miejsce definiujące wspierane typy TTS i ich pola — Single Source of
        Truth (mirror `LLMFactory.get_all_schemas()`)."""
        return ProviderMetadataResponse(
            provider_types=[
                ProviderTypeSpecDTO(
                    type="ELEVENLABS",
                    label="ElevenLabs (chmura)",
                    options_schema=[
                        ProviderOptionSpec(
                            name="api_key",
                            label="Klucz API (API Key)",
                            type="password",
                            required=True,
                            default_value="",
                            placeholder="sk_...",
                        ),
                        ProviderOptionSpec(
                            name="voice_id",
                            label="ID głosu",
                            type="string",
                            required=True,
                            default_value="pNInz6obpgDQGcFmaJgB",
                            placeholder="pNInz6obpgDQGcFmaJgB",
                        ),
                        ProviderOptionSpec(
                            name="model_id",
                            label="Model TTS",
                            type="string",
                            required=True,
                            default_value="eleven_multilingual_v2",
                            placeholder="eleven_multilingual_v2",
                        ),
                    ],
                ),
            ]
        )
