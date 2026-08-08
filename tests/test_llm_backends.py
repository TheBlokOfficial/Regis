import pytest
from unittest.mock import patch
import os

from controller.providers.llm.ollama import OllamaBackend
from controller.providers.llm.openrouter import OpenRouterBackend
import controller.providers.llm.resolver as providers

@patch("requests.get")
def test_ollama_is_available_true(mock_get):
    mock_get.return_value.status_code = 200
    backend = OllamaBackend(model_name="test")
    assert backend.is_available() is True

@patch("requests.get")
def test_ollama_is_available_false(mock_get):
    mock_get.return_value.status_code = 500
    backend = OllamaBackend(model_name="test")
    assert backend.is_available() is False

def test_openrouter_is_available_true():
    backend = OpenRouterBackend(api_key="test_key", model_name="test_model")
    assert backend.is_available() is True

def test_openrouter_is_available_false():
    backend = OpenRouterBackend(api_key="", model_name="")
    assert backend.is_available() is False

@patch.object(OpenRouterBackend, "is_available", return_value=True)
@patch("controller.providers.llm.resolver.endpoints_cloud.get_cloud_providers")
def test_get_llm_backend_returns_openrouter(mock_get_cloud, mock_openrouter_avail):
    mock_get_cloud.return_value = [{
        "id": "test",
        "type": "openrouter",
        "api_key": "test_key",
        "model": "test_model",
        "priority": 50
    }]
    backend = providers.get_llm_backend()
    assert isinstance(backend, OpenRouterBackend)

from controller.providers.llm.client_app import ClientAppBackend

@patch.object(OpenRouterBackend, "is_available", return_value=False)
@patch("controller.providers.llm.resolver.endpoints_cloud.get_cloud_providers", return_value=[])
def test_get_llm_backend_returns_client_app_if_registered(mock_get_cloud, mock_openrouter_avail):
    providers.client_registry.client_registry = {"worker_1": {"id": "worker_1", "priority": 10, "model_name": "qwen3.5:9b"}}
    backend = providers.get_llm_backend()
    assert isinstance(backend, ClientAppBackend)
    assert backend.model_name == "qwen3.5:9b"
    providers.client_registry.client_registry.clear()
    
@patch.object(OpenRouterBackend, "is_available", return_value=False)
@patch("controller.providers.llm.resolver.endpoints_cloud.get_cloud_providers", return_value=[])
def test_get_llm_backend_returns_none_if_no_worker(mock_get_cloud, mock_openrouter_avail):
    providers.client_registry.client_registry = {}
    backend = providers.get_llm_backend()
    assert backend is None


def test_build_messages_from_history_handles_tool_dicts_and_filters_raw_logs():
    from controller.agent.session.history import build_messages_from_history

    history = [
        {
            "user": "Wyłącz światło",
            "assistant": "Światło wyłączone.",
            "tools": [
                # Stary napisowy log CLI - powinien zostać zignorowany
                "< Kontroler zwrócił: {\"result\": \"success\"}",
                # Nowa struktura słownikowa - powinna być poprawnie rozbita na <action> i <tool_response>
                {
                    "thought": "Wyłączam światło w pracowni",
                    "name": "execute_action",
                    "arguments": {"action": "turn_off", "entity_id": ["light.pracownia"]},
                    "result": "{\"result\": \"success\"}"
                }
            ],
            "timestamp": "12:00:00"
        }
    ]

    messages = build_messages_from_history("System Prompt", history, current_message="Włącz światło")

    # Powinny być: System prompt, User prompt, Assistant final, Current User message
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[1]["content"] == "Wyłącz światło"
    assert messages[2]["content"] == "Światło wyłączone."
    assert messages[3]["content"] == "Włącz światło"

    # Upewnijmy się, że żaden komunikat assistant nie zawiera surowego napisowego logu CLI
    for m in messages:
        if m["role"] == "assistant":
            assert "< Kontroler zwrócił:" not in m["content"]


def test_openrouter_accumulate_tool_call():
    accumulator = {}

    # Chunk 1: inicjalizacja nazwy i id
    chunk_1 = {
        "index": 0,
        "id": "call_abc123",
        "function": {"name": "execute_action", "arguments": '{"action":'}
    }
    OpenRouterBackend._accumulate_tool_call(accumulator, chunk_1, 0)

    assert 0 in accumulator
    assert accumulator[0]["id"] == "call_abc123"
    assert accumulator[0]["function"]["name"] == "execute_action"
    assert accumulator[0]["function"]["arguments"] == '{"action":'

    # Chunk 2: doklejenie argumentów
    chunk_2 = {
        "index": 0,
        "function": {"arguments": ' "turn_on"}'}
    }
    OpenRouterBackend._accumulate_tool_call(accumulator, chunk_2, 0)

    assert accumulator[0]["function"]["arguments"] == '{"action": "turn_on"}'


def test_run_agent_loop_simple():
    import asyncio
    from controller.agent.engine import run_agent_loop

    class MockStreamProvider:
        def chat_stream(self, messages, tools=None):
            yield {"type": "content", "content": "Cześć!"}

    async def _test():
        q = asyncio.Queue()
        loop = asyncio.get_running_loop()
        session_history = [{"role": "user", "content": "Hej"}]

        return await run_agent_loop(
            stream_provider=MockStreamProvider(),
            session_history=session_history,
            user_message="Hej",
            satellite_id="test_sat",
            room="salon",
            worker_id="test_worker",
            model_name="test_model",
            q=q,
            loop=loop,
        )

    result = asyncio.run(_test())
    assert result == "Cześć!"
