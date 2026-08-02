import pytest
from unittest.mock import patch
import os

from controller.llm_backends.ollama import OllamaBackend
from controller.openrouter_backend import OpenRouterBackend
import controller.providers as providers
import controller.registry as registry

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
def test_get_llm_backend_returns_openrouter(mock_openrouter_avail):
    providers._cloud_providers_cache = [{
        "id": "test",
        "type": "openrouter",
        "api_key": "test_key",
        "model": "test_model",
        "priority": 50
    }]
    providers._providers_loaded = True
    backend = providers.get_llm_backend()
    assert isinstance(backend, OpenRouterBackend)

@patch.object(OpenRouterBackend, "is_available", return_value=False)
def test_get_llm_backend_returns_ollama_if_worker_registered(mock_openrouter_avail):
    providers._cloud_providers_cache = []
    providers._providers_loaded = True
    registry.worker_registry = {"worker_1": {"id": "worker_1", "priority": 10}}
    backend = providers.get_llm_backend()
    assert isinstance(backend, OllamaBackend)
    assert backend.model_name == "worker"
    
@patch.object(OpenRouterBackend, "is_available", return_value=False)
def test_get_llm_backend_returns_none_if_no_worker(mock_openrouter_avail):
    providers._cloud_providers_cache = []
    providers._providers_loaded = True
    registry.worker_registry = {}
    backend = providers.get_llm_backend()
    assert backend is None


def test_build_messages_from_history_handles_tool_dicts_and_filters_raw_logs():
    from node.utils import build_messages_from_history

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


