import httpx
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from server.agent.llm import LLMMessage
from server.ai.llm.models import BackendInstanceConfig, ProviderType
from server.ai.llm.factory import LLMFactory
from server.ai.llm.providers.ollama import OllamaProvider
from server.ai.llm.providers.openai_compatible import OpenAICompatibleProvider


@pytest.mark.anyio
async def test_ollama_provider_max_tokens_num_predict():
    provider = OllamaProvider(base_url="http://localhost:11434", model="llama3", max_tokens=8192)
    assert provider.max_tokens == 8192

    messages = [LLMMessage(role="user", content="Hello")]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_lines():
        yield '{"message": {"content": "World"}}'

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
        assert "".join(chunks) == "World"

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
    mock_response.raise_for_status = MagicMock()

    async def mock_aiter_lines():
        yield 'data: {"choices": [{"delta": {"content": "Hi"}}]}'
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
        assert "".join(chunks) == "Hi"

        mock_client.stream.assert_called_once()
        call_args = mock_client.stream.call_args
        assert call_args.args[1] == f"{base_url}/chat/completions"

        json_payload = call_args.kwargs.get("json", {})
        assert json_payload.get("max_tokens") == 2048
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
    """Regresja: `raise_for_status()` rzuca w trakcie strumieniowania — dostęp do
    `e.response.text` bez wcześniejszego `aread()` maskował prawdziwy błąd API
    komunikatem httpx "Attempted to access streaming response content, without
    having called read()." (patrz historia gita, zgłoszone na żywo w UI)."""
    provider = OpenAICompatibleProvider(base_url="https://api.example.com/v1", api_key="test-key", model="m")
    messages = [LLMMessage(role="user", content="Hello")]

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.aread = AsyncMock()
    mock_response.text = '{"error": "invalid request: bad tool_call_id"}'
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("Bad Request", request=MagicMock(), response=mock_response)
    )

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

    assert "invalid request: bad tool_call_id" in str(exc_info.value)
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


def test_llm_factory_schemas_include_max_tokens():
    schemas = LLMFactory.get_all_schemas()
    for provider_type in schemas.provider_types:
        opt_names = [opt.name for opt in provider_type.options_schema]
        assert "max_tokens" in opt_names
