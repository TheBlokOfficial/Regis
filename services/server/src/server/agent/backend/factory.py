from shared import get_logger, ProviderMetadataResponse, ProviderTypeSpecDTO, ProviderOptionSpec
from server.agent.backend.models import BackendInstanceConfig, ProviderType
from server.agent.backend.providers import BaseLLMProvider, OllamaProvider, OpenRouterProvider

logger = get_logger("regis.agent.backends.factory")


class LLMFactory:
    """Fabryka do tworzenia instancji dostawców LLM z obiektów konfiguracji."""

    @staticmethod
    def create_provider(config: BackendInstanceConfig, default_timeout: float = 30.0) -> BaseLLMProvider:
        """Tworzy i zwraca instancję BaseLLMProvider dopasowaną do podanej konfiguracji.

        :param config: Obiekt BackendInstanceConfig opisujący dane instancji.
        :param default_timeout: Domyślny timeout (w sekundach) gdy opcje nie zawierają wartości.
        :return: Wygenerowana instancja dostawcy LLM.
        """
        logger.info(
            f"Tworzenie instancji dostawcy LLM '{config.name}' "
            f"[ID: {config.id}, Typ: {config.type.value}]..."
        )

        if config.type == ProviderType.OLLAMA:
            return OllamaProvider(
                base_url=config.options.get("base_url", "http://localhost:11434"),
                model=config.options.get("model", "llama3"),
                timeout=float(config.options.get("timeout", default_timeout)),
            )
        elif config.type == ProviderType.OPENROUTER:
            return OpenRouterProvider(
                api_key=config.options.get("api_key", ""),
                model=config.options.get("model", "anthropic/claude-3.5-sonnet"),
                base_url=config.options.get("base_url", "https://openrouter.ai/api/v1"),
                timeout=float(config.options.get("timeout", default_timeout)),
            )
        else:
            raise ValueError(f"Nieobsługiwany typ dostawcy LLM: {config.type}")

    @staticmethod
    def get_all_schemas() -> ProviderMetadataResponse:
        """Zwraca schematy opcji konfiguracyjnych dla wszystkich wspieranych typów dostawców LLM.

        Jedyne miejsce w systemie definiujące wspierane typy i ich pola — Single Source of Truth.
        Dodając nowego dostawcę wystarczy rozszerzyć tę metodę oraz dodać gałąź w create_provider().
        """
        return ProviderMetadataResponse(
            provider_types=[
                ProviderTypeSpecDTO(
                    type="OLLAMA",
                    label="Lokalna Ollama",
                    options_schema=[
                        ProviderOptionSpec(
                            name="model",
                            label="Model LLM",
                            type="string",
                            required=True,
                            default_value="llama3",
                            placeholder="llama3",
                        ),
                        ProviderOptionSpec(
                            name="base_url",
                            label="Base URL",
                            type="string",
                            required=True,
                            default_value="http://localhost:11434",
                            placeholder="http://localhost:11434",
                        ),
                    ],
                ),
                ProviderTypeSpecDTO(
                    type="OPENROUTER",
                    label="OpenRouter (API)",
                    options_schema=[
                        ProviderOptionSpec(
                            name="model",
                            label="Model LLM",
                            type="string",
                            required=True,
                            default_value="anthropic/claude-3.5-sonnet",
                            placeholder="anthropic/claude-3.5-sonnet",
                        ),
                        ProviderOptionSpec(
                            name="api_key",
                            label="Klucz API (API Key)",
                            type="password",
                            required=True,
                            default_value="",
                            placeholder="sk-or-v1-...",
                        ),
                        ProviderOptionSpec(
                            name="base_url",
                            label="Base URL",
                            type="string",
                            required=False,
                            default_value="https://openrouter.ai/api/v1",
                            placeholder="https://openrouter.ai/api/v1",
                        ),
                    ],
                ),
            ]
        )
