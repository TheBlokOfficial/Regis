import pytest
from unittest.mock import patch
import os

from core.llm_backends.ollama import OllamaBackend
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

def test_openrouter_is_available_true(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test_key")
    monkeypatch.setenv("OPENROUTER_MODEL", "test_model")
    backend = OpenRouterBackend()
    assert backend.is_available() is True

def test_openrouter_is_available_false(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    backend = OpenRouterBackend()
    assert backend.is_available() is False

@patch.object(OpenRouterBackend, "is_available", return_value=True)
def test_get_llm_backend_returns_openrouter(mock_openrouter_avail):
    backend = providers.get_llm_backend()
    assert isinstance(backend, OpenRouterBackend)

@patch.object(OpenRouterBackend, "is_available", return_value=False)
def test_get_llm_backend_returns_ollama_if_worker_registered(mock_openrouter_avail):
    registry.worker_registry = {"worker_1": {"id": "worker_1"}}
    backend = providers.get_llm_backend()
    assert isinstance(backend, OllamaBackend)
    assert backend.model_name == "worker"
    
@patch.object(OpenRouterBackend, "is_available", return_value=False)
def test_get_llm_backend_returns_none_if_no_worker(mock_openrouter_avail):
    registry.worker_registry = {}
    backend = providers.get_llm_backend()
    assert backend is None
