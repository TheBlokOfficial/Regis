from shared import get_logger
from server.config import load_settings
from server.agent.backend.models import BackendInstanceConfig, ProviderType
from server.agent.backend.providers import BaseLLMProvider, OllamaProvider, OpenRouterProvider

logger = get_logger("regis.agent.backends.factory")


class LLMFactory:
    """Fabryka do tworzenia instancji dostawców LLM z obiektów konfiguracji."""

    @staticmethod
    def create_provider(config: BackendInstanceConfig) -> BaseLLMProvider:
        """Tworzy i zwraca instancję BaseLLMProvider dopasowaną do podanej konfiguracji.

        :param config: Obiekt BackendInstanceConfig opisujący dane instancji.
        :return: Wygenerowana instancja dostawcy LLM.
        """
        settings = load_settings()
        default_timeout = settings.llm_timeout

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
