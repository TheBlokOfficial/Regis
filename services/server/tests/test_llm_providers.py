import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from server.agent.backend.models import BackendInstanceConfig, ProviderType
from server.agent.backend.factory import LLMFactory
from server.agent.backend.providers.base import LLMMessage
from server.agent.backend.providers.ollama import OllamaProvider
from server.agent.backend.providers.openrouter import OpenRouterProvider


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


@pytest.mark.anyio
async def test_openrouter_provider_max_tokens():
    provider = OpenRouterProvider(api_key="test-key", model="claude-3.5", max_tokens=2048)
    assert provider.max_tokens == 2048

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
        
        # Sprawdzamy czy w wysłanym payloadzie znajduje się max_tokens = 2048
        mock_client.stream.assert_called_once()
        call_kwargs = mock_client.stream.call_args.kwargs
        json_payload = call_kwargs.get("json", {})
        assert json_payload.get("max_tokens") == 2048


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
    assert isinstance(provider_openrouter, OpenRouterProvider)
    assert provider_openrouter.max_tokens == 16384


def test_llm_factory_schemas_include_max_tokens():
    schemas = LLMFactory.get_all_schemas()
    for provider_type in schemas.provider_types:
        opt_names = [opt.name for opt in provider_type.options_schema]
        assert "max_tokens" in opt_names
