from typing import Any

from shared import ProviderMetadataResponse, ProviderOptionSpec, ProviderTypeSpecDTO, get_logger

from server.ai.llm.models import BackendInstanceConfig, ProviderType
from server.ai.llm.providers import OllamaProvider, OpenAICompatibleProvider
from server.ports.llm import BaseLLMProvider

logger = get_logger("regis.ai.llm.factory")


def _number(options: dict[str, Any], key: str) -> float | int | None:
    """Opcje przychodzą z formularza jako stringi. Puste pole znaczy "nie wysyłaj tego
    parametru w ogóle" — a nie "wyślij zero", co byłoby realną zmianą zachowania modelu."""
    raw = options.get(key)
    if raw is None or not str(raw).strip():
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.warning(f"Nieprawidłowa wartość '{key}': '{raw}'. Pomijam.")
        return None
    return int(value) if value.is_integer() else value


def _text(options: dict[str, Any], key: str) -> str | None:
    raw = options.get(key)
    value = str(raw).strip() if raw is not None else ""
    return value or None


def _flag(options: dict[str, Any], key: str) -> bool | None:
    raw = options.get(key)
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _openai_generation_payload(options: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Parametry generacji, które API OpenAI-compatible przyjmuje wprost, na najwyższym
    poziomie payloadu. Które z nich są sensowne dla danego modelu, rozstrzyga formularz
    (`ai/llm/model_catalog.py`) — fabryka tylko przepisuje to, co użytkownik ustawił."""
    payload: dict[str, Any] = {}
    for key in keys:
        value = _number(options, key)
        if value is not None:
            payload[key] = value
    return payload


class LLMFactory:
    """Fabryka do tworzenia instancji dostawców LLM z obiektów konfiguracji."""

    @staticmethod
    def create_provider(config: BackendInstanceConfig) -> BaseLLMProvider:
        """Tworzy i zwraca instancję BaseLLMProvider dopasowaną do podanej konfiguracji.

        :param config: Obiekt BackendInstanceConfig opisujący dane instancji.
        :return: Wygenerowana instancja dostawcy LLM.
        """
        logger.info(
            f"Tworzenie instancji dostawcy LLM '{config.name}' "
            f"[ID: {config.id}, Typ: {config.type.value}]..."
        )

        options = config.options
        max_tokens_value = _number(options, "max_tokens")
        max_tokens = int(max_tokens_value) if max_tokens_value is not None else None

        if config.type == ProviderType.OLLAMA:
            # Ollama trzyma parametry generacji w zagnieżdżonym worku `options`, a nie na
            # najwyższym poziomie payloadu — stąd osobna ścieżka zamiast wspólnej mapy.
            ollama_options = {
                key: value
                for key in ("temperature", "top_p", "top_k", "num_ctx", "repeat_penalty")
                if (value := _number(options, key)) is not None
            }
            num_predict = _number(options, "num_predict")
            if num_predict is not None:
                ollama_options["num_predict"] = int(num_predict)
            think = _text(options, "think")
            return OllamaProvider(
                base_url=options.get("base_url", "http://localhost:11434"),
                model=options.get("model", "llama3"),
                max_tokens=max_tokens,
                options=ollama_options,
                # "off"/"on" to nasze etykiety formularza; Ollama chce boola albo poziomu.
                think={"off": False, "on": True}.get(think, think) if think else None,
            )
        elif config.type == ProviderType.OPENROUTER:
            extra_payload = _openai_generation_payload(
                options,
                ("temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty", "repetition_penalty"),
            )
            # OpenRouter przyjmuje głębokość rozumowania jako zagnieżdżony obiekt.
            # Wcześniej było tu zahardkodowane `{"effort": "none"}` dla KAŻDEGO modelu —
            # czyli akurat ten parametr, który chce się stroić, był nietykalny.
            if (effort := _text(options, "reasoning_effort")) is not None:
                extra_payload["reasoning"] = {"effort": effort}
            return OpenAICompatibleProvider(
                base_url="https://openrouter.ai/api/v1",
                api_key=options.get("api_key", ""),
                model=options.get("model", "anthropic/claude-3.5-sonnet"),
                max_tokens=max_tokens,
                extra_headers={
                    "HTTP-Referer": "https://github.com/TheBlokOfficial/Regis",
                    "X-Title": "Regis OS",
                },
                extra_payload=extra_payload,
            )
        elif config.type == ProviderType.GROQ:
            extra_payload = _openai_generation_payload(options, ("temperature", "top_p"))
            # Groq przyjmuje te same pojęcia pod PŁASKIMI nazwami, nie w obiekcie
            # `reasoning` — to nie jest ta sama rzecz co u OpenRoutera, mimo wspólnego
            # formatu Chat Completions.
            if (effort := _text(options, "reasoning_effort")) is not None:
                extra_payload["reasoning_effort"] = effort
            if (reasoning_format := _text(options, "reasoning_format")) is not None:
                extra_payload["reasoning_format"] = reasoning_format
            if (include_reasoning := _flag(options, "include_reasoning")) is not None:
                extra_payload["include_reasoning"] = include_reasoning
            return OpenAICompatibleProvider(
                base_url="https://api.groq.com/openai/v1",
                api_key=options.get("api_key", ""),
                model=options.get("model", "openai/gpt-oss-120b"),
                max_tokens=max_tokens,
                extra_payload=extra_payload,
            )
        else:
            raise ValueError(f"Nieobsługiwany typ dostawcy LLM: {config.type}")

    @staticmethod
    def get_all_schemas() -> ProviderMetadataResponse:
        """Pola NIEZALEŻNE od modelu — klucz API, adres serwera. To wszystko, co da się
        powiedzieć o dostawcy, nie wiedząc jeszcze, którego modelu użyje.

        Parametry generacji NIE są tutaj: są per model i przychodzą z
        `GET /api/v1/llm/providers/{id}/models` (`ai/llm/model_catalog.py`). Dawna wersja
        trzymała tu wspólną trójkę `model`/`api_key`/`max_tokens` dla wszystkich typów —
        i to był dokładnie sufit, przez który nie dało się wystawić `reasoning_effort`
        istniejącego tylko dla części modeli.
        """
        return ProviderMetadataResponse(
            provider_types=[
                ProviderTypeSpecDTO(
                    type="OLLAMA",
                    label="Lokalna Ollama",
                    supports_model_discovery=True,
                    options_schema=[
                        ProviderOptionSpec(
                            name="base_url",
                            label="Adres serwera",
                            type="string",
                            required=True,
                            default_value="http://localhost:11434",
                            placeholder="http://localhost:11434",
                            hint="Self-hosted, więc adres jest edytowalny — w odróżnieniu od dostawców chmurowych.",
                        ),
                    ],
                ),
                ProviderTypeSpecDTO(
                    type="OPENROUTER",
                    label="OpenRouter (API)",
                    supports_model_discovery=True,
                    options_schema=[
                        ProviderOptionSpec(
                            name="api_key",
                            label="Klucz API",
                            type="password",
                            required=True,
                            default_value="",
                            placeholder="sk-or-v1-...",
                            hint="Pozostaw puste przy edycji, żeby zachować obecny klucz.",
                        ),
                    ],
                ),
                ProviderTypeSpecDTO(
                    type="GROQ",
                    label="Groq (API)",
                    supports_model_discovery=True,
                    options_schema=[
                        ProviderOptionSpec(
                            name="api_key",
                            label="Klucz API",
                            type="password",
                            required=True,
                            default_value="",
                            placeholder="gsk_...",
                            hint="Pozostaw puste przy edycji, żeby zachować obecny klucz.",
                        ),
                    ],
                ),
            ]
        )
