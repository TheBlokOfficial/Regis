from shared import ProviderMetadataResponse, ProviderOptionSpec, ProviderTypeSpecDTO, get_logger

from server.ai.stt.models import STTInstanceConfig, STTProviderType
from server.ai.stt.providers import GroqSTTProvider
from server.ports.stt import BaseSTTProvider

logger = get_logger("regis.ai.stt.factory")


class STTNotConfiguredError(RuntimeError):
    """Backend STT aktywny, ale bez wymaganych danych (np. pustego `api_key`) —
    świadomie NIE degradujemy po cichu do `MockSTTProvider`: satelita nagrywa
    realną mowę, więc podstawienie sfabrykowanego tekstu wygenerowałoby prawdziwą
    turę agenta na podstawie czegoś, czego użytkownik nigdy nie powiedział."""


class STTFactory:
    """Fabryka do tworzenia instancji dostawców STT z obiektów konfiguracji.
    Mirror `ai.llm.factory.LLMFactory`."""

    @staticmethod
    def create_provider(config: STTInstanceConfig) -> BaseSTTProvider:
        logger.info(f"Tworzenie instancji dostawcy STT '{config.name}' [ID: {config.id}, Typ: {config.type.value}]...")

        if config.type == STTProviderType.GROQ:
            api_key = config.options.get("api_key", "")
            if not api_key:
                raise STTNotConfiguredError(
                    f"Backend STT '{config.name}' [ID: {config.id}] nie ma ustawionego klucza API."
                )
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
