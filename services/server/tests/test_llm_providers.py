from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from server.ai.llm.factory import LLMFactory
from server.ai.llm.model_catalog import (
    _groq_params_for,
    _ollama_params_for,
    _openrouter_params_for,
    fallback_options_schema,
)
from server.ai.llm.models import BackendInstanceConfig, ProviderType
from server.ai.llm.providers.ollama import OllamaProvider
from server.ai.llm.providers.openai_compatible import OpenAICompatibleProvider
from server.ports.llm import GenerationUsage, LLMMessage


@pytest.mark.anyio
async def test_ollama_provider_max_tokens_num_predict():
    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3", max_tokens=8192)
    assert provider.max_tokens == 8192

    messages = [LLMMessage(role="user", content="Hello")]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_lines():
        yield '{"message": {"content": "World"}}'
        yield '{"message": {"content": ""}, "done": true, "done_reason": "stop", "prompt_eval_count": 11, "eval_count": 3}'

    mock_response.aiter_lines = mock_aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_stream_ctx

    mock_async_client_ctx = MagicMock()
    mock_async_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_async_client_ctx):
        chunks = [chunk async for chunk in provider.generate_stream(messages)]
        assert "".join(c for c in chunks if isinstance(c, str)) == "World"

        # Rozliczenie generacji: JEDNO, terminalne zdarzenie na końcu strumienia.
        usage = [c for c in chunks if isinstance(c, GenerationUsage)]
        assert len(usage) == 1
        assert chunks[-1] is usage[0]
        assert usage[0].prompt_tokens == 11
        assert usage[0].completion_tokens == 3
        assert usage[0].finish_reason == "stop"
        # Ollama nie zna pojęcia cache promptu — `None`, nigdy 0 (patrz `GenerationUsage`).
        assert usage[0].cached_tokens is None

        # Sprawdzamy czy w wysłanym payloadzie w options znajduje się num_predict = 8192
        mock_client.stream.assert_called_once()
        call_kwargs = mock_client.stream.call_args.kwargs
        json_payload = call_kwargs.get("json", {})
        assert "options" in json_payload
        assert json_payload["options"].get("num_predict") == 8192


# Dwa realne przypadki tego samego OpenAICompatibleProvider — OpenRouter dokłada
# nagłówki HTTP-Referer/X-Title i pole payloadu "reasoning", Groq nie dokłada nic.
@pytest.mark.anyio
@pytest.mark.parametrize(
    "base_url,extra_headers,extra_payload",
    [
        (
            "https://openrouter.ai/api/v1",
            {"HTTP-Referer": "https://github.com/TheBlokOfficial/Regis", "X-Title": "Regis OS"},
            {"reasoning": {"effort": "none"}},
        ),
        ("https://api.groq.com/openai/v1", None, None),
    ],
    ids=["openrouter", "groq"],
)
async def test_openai_compatible_provider_streams_and_applies_extras(base_url, extra_headers, extra_payload):
    provider = OpenAICompatibleProvider(
        base_url=base_url,
        api_key="test-key",
        model="test-model",
        max_tokens=2048,
        extra_headers=extra_headers,
        extra_payload=extra_payload,
    )
    assert provider.max_tokens == 2048
    assert provider.base_url == base_url

    messages = [LLMMessage(role="user", content="Hello")]

    mock_response = MagicMock()
    mock_response.is_error = False

    async def mock_aiter_lines():
        yield 'data: {"model": "test-model", "choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]}'
        # Blok `usage` przychodzi w OSOBNYM chunku, z pustą listą `choices` — dokładnie
        # ten kształt gubiła poprzednia wersja parsera (odczyt tylko wewnątrz `if choices`).
        yield 'data: {"model": "test-model", "choices": [], "usage": {"prompt_tokens": 42, "completion_tokens": 7, "prompt_tokens_details": {"cached_tokens": 16}}}'
        yield 'data: [DONE]'

    mock_response.aiter_lines = mock_aiter_lines

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_stream_ctx

    mock_async_client_ctx = MagicMock()
    mock_async_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_async_client_ctx):
        chunks = [chunk async for chunk in provider.generate_stream(messages)]
        assert "".join(c for c in chunks if isinstance(c, str)) == "Hi"

        usage = [c for c in chunks if isinstance(c, GenerationUsage)]
        assert len(usage) == 1
        assert chunks[-1] is usage[0]
        assert usage[0].prompt_tokens == 42
        assert usage[0].completion_tokens == 7
        assert usage[0].cached_tokens == 16
        assert usage[0].finish_reason == "stop"

        mock_client.stream.assert_called_once()
        call_args = mock_client.stream.call_args
        assert call_args.args[1] == f"{base_url}/chat/completions"

        json_payload = call_args.kwargs.get("json", {})
        assert json_payload.get("max_tokens") == 2048
        # Bez tego opt-inu żaden dostawca z tej rodziny nie przyśle bloku `usage`.
        assert json_payload.get("stream_options") == {"include_usage": True}
        headers = call_args.kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer test-key"

        if extra_payload:
            for key, value in extra_payload.items():
                assert json_payload.get(key) == value
        else:
            assert "reasoning" not in json_payload

        if extra_headers:
            for key, value in extra_headers.items():
                assert headers.get(key) == value
        else:
            assert "HTTP-Referer" not in headers


@pytest.mark.anyio
async def test_openai_compatible_provider_surfaces_http_error_body_not_stream_consumed_error():
    """Regresja: treść błędu HTTP musi być odczytana (`aread()`) wewnątrz
    `async with client.stream(...)`, zanim ten blok się zakończy — po jego
    zakończeniu httpx zamyka połączenie i odczyt nie jest już możliwy (pierwsza
    wersja fixa robiła to poza blokiem, dalej gubiąc treść błędu; zgłoszone na
    żywo w UI, HTTP 429 z Groq)."""
    provider = OpenAICompatibleProvider(base_url="https://api.example.com/v1", api_key="test-key", model="m")
    messages = [LLMMessage(role="user", content="Hello")]

    mock_response = MagicMock()
    mock_response.status_code = 429
    mock_response.is_error = True
    mock_response.aread = AsyncMock(return_value=b'{"error": "rate limit exceeded"}')

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
    mock_stream_ctx.__aexit__ = AsyncMock(return_value=None)

    mock_client = MagicMock()
    mock_client.stream.return_value = mock_stream_ctx

    mock_async_client_ctx = MagicMock()
    mock_async_client_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_async_client_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_async_client_ctx):
        with pytest.raises(RuntimeError) as exc_info:
            async for _ in provider.generate_stream(messages):
                pass

    assert "rate limit exceeded" in str(exc_info.value)
    assert "429" in str(exc_info.value)
    assert "Attempted to access streaming response content" not in str(exc_info.value)
    mock_response.aread.assert_awaited_once()


def test_llm_factory_creates_provider_with_max_tokens():
    config_ollama = BackendInstanceConfig(
        id="ollama_test",
        type=ProviderType.OLLAMA,
        name="Ollama Test",
        options={"base_url": "http://localhost:11434", "model": "llama3", "max_tokens": "4096"},
    )
    provider_ollama = LLMFactory.create_provider(config_ollama)
    assert isinstance(provider_ollama, OllamaProvider)
    assert provider_ollama.max_tokens == 4096

    config_openrouter = BackendInstanceConfig(
        id="openrouter_test",
        type=ProviderType.OPENROUTER,
        name="OpenRouter Test",
        options={"api_key": "test_key", "model": "gpt-4o", "max_tokens": 16384},
    )
    provider_openrouter = LLMFactory.create_provider(config_openrouter)
    assert isinstance(provider_openrouter, OpenAICompatibleProvider)
    assert provider_openrouter.max_tokens == 16384
    assert provider_openrouter.base_url == "https://openrouter.ai/api/v1"

    config_groq = BackendInstanceConfig(
        id="groq_test",
        type=ProviderType.GROQ,
        name="Groq Test",
        options={"api_key": "test_key", "model": "llama-3.3-70b-versatile", "max_tokens": 8192},
    )
    provider_groq = LLMFactory.create_provider(config_groq)
    assert isinstance(provider_groq, OpenAICompatibleProvider)
    assert provider_groq.max_tokens == 8192
    assert provider_groq.base_url == "https://api.groq.com/openai/v1"


def test_type_schema_holds_only_model_independent_fields():
    """Schemat typu opisuje to, co da się powiedzieć o dostępcy NIE wiedząc jeszcze,
    którego modelu użyje: klucz API, adres serwera. Parametry generacji są per model
    i przychodzą z `GET .../providers/{id}/models` — wspólna lista dla wszystkich typów
    była dokładnie tym sufitem, przez który nie dało się wystawić `reasoning_effort`."""
    schemas = LLMFactory.get_all_schemas()

    assert {t.type for t in schemas.provider_types} == {"OLLAMA", "OPENROUTER", "GROQ"}
    for provider_type in schemas.provider_types:
        opt_names = {opt.name for opt in provider_type.options_schema}
        assert opt_names <= {"api_key", "base_url"}, provider_type.type
        assert provider_type.supports_model_discovery is True


def test_every_type_can_configure_output_limit_for_a_hand_typed_model():
    """Lista modeli nigdy nie zamyka wyboru — dla modelu wpisanego z ręki też musi
    istnieć formularz, i musi się w nim dać ustawić limit długości odpowiedzi."""
    for provider_type in ProviderType:
        names = {opt.name for opt in fallback_options_schema(provider_type)}
        # Ollama nazywa ten sam parametr `num_predict` — to jej własne słownictwo, nie alias.
        assert names & {"max_tokens", "num_predict"}, provider_type
        assert "temperature" in names, provider_type


def test_gpt_oss_gets_reasoning_effort_and_llama_does_not():
    """Sedno per-modelowych formularzy: `reasoning_effort` istnieje dla gpt-oss i nie
    istnieje dla modelu bez rozumowania — jedna wspólna lista pól nie opisałaby obu."""
    gpt_oss = {opt.name for opt in _groq_params_for("openai/gpt-oss-120b")}
    llama = {opt.name for opt in _groq_params_for("llama-3.3-70b-versatile")}

    assert "reasoning_effort" in gpt_oss
    assert "include_reasoning" in gpt_oss
    assert "reasoning_effort" not in llama
    assert "temperature" in llama


def test_qwen_on_groq_gets_different_reasoning_values_than_gpt_oss():
    """Ten sam parametr, inny zestaw wartości zależnie od rodziny modelu — dowód, że
    tabela musi być per rodzina, a nie per dostawca."""

    def values(model_id: str) -> set[str]:
        spec = next(o for o in _groq_params_for(model_id) if o.name == "reasoning_effort")
        return {choice.value for choice in spec.choices}

    assert values("openai/gpt-oss-120b") == {"low", "medium", "high"}
    assert values("qwen/qwen3-32b") == {"none", "default"}


def test_ollama_think_offered_only_for_thinking_families():
    assert "think" in {opt.name for opt in _ollama_params_for("qwen3:8b")}
    assert "think" in {opt.name for opt in _ollama_params_for("custom-tag", family="deepseek-r1")}
    assert "think" not in {opt.name for opt in _ollama_params_for("gemma4:26b")}


def test_openrouter_form_is_built_from_supported_parameters():
    """Formularz OpenRoutera pochodzi wprost z `supported_parameters` modelu, więc nie
    gnije — ale bierzemy tylko te parametry, które Regis realnie umie wysłać."""
    names = {opt.name for opt in _openrouter_params_for(["temperature", "reasoning_effort", "logit_bias", "seed"])}

    assert "temperature" in names
    assert "reasoning_effort" in names
    # Nieobsługiwane przez Regis — pokazanie ich byłoby obietnicą bez pokrycia.
    assert "logit_bias" not in names
    assert "seed" not in names
