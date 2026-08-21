from shared import get_logger, ProviderMetadataResponse, ProviderTypeSpecDTO, ProviderOptionSpec
from server.ai.stt.models import STTInstanceConfig, STTProviderType
from server.ai.stt.providers import GroqSTTProvider, MockSTTProvider
from server.voice.stt import BaseSTTProvider

logger = get_logger("regis.ai.stt.factory")


class STTFactory:
    """Fabryka do tworzenia instancji dostawców STT z obiektów konfiguracji.
    Mirror `ai.llm.factory.LLMFactory`."""

    @staticmethod
    def create_provider(config: STTInstanceConfig) -> BaseSTTProvider:
        logger.info(f"Tworzenie instancji dostawcy STT '{config.name}' [ID: {config.id}, Typ: {config.type.value}]...")

        if config.type == STTProviderType.GROQ:
            api_key = config.options.get("api_key", "")
            if not api_key:
                # Pusty klucz -> łagodna degradacja do dev-providera (ten sam wzorzec co
                # dawny `main.py::_build_stt_provider`, teraz per-instancja).
                return MockSTTProvider()
            return GroqSTTProvider(api_key=api_key, model=config.options.get("model", "whisper-large-v3-turbo"))
        else:
            raise ValueError(f"Nieobsługiwany typ dostawcy STT: {config.type}")

    @staticmethod
    def get_all_schemas() -> ProviderMetadataResponse:
        """Jedyne miejsce definiujące wspierane typy STT i ich pola — Single Source of
        Truth (mirror `LLMFactory.get_all_schemas()`)."""
        return ProviderMetadataResponse(
            provider_types=[
                ProviderTypeSpecDTO(
                    type="GROQ",
                    label="Groq (Whisper, chmura)",
                    options_schema=[
                        ProviderOptionSpec(
                            name="api_key",
                            label="Klucz API (API Key)",
                            type="password",
                            required=True,
                            default_value="",
                            placeholder="gsk_...",
                        ),
                        ProviderOptionSpec(
                            name="model",
                            label="Model STT",
                            type="string",
                            required=True,
                            default_value="whisper-large-v3-turbo",
                            placeholder="whisper-large-v3-turbo",
                        ),
                    ],
                ),
            ]
        )
