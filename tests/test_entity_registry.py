"""Testy jednostkowe dla Rejestru Encji.

Testują:
- Model WorkerRegistrationRequest (walidacja payloadu)
- Logikę wyboru węzła (_pick_worker) przez bezpośrednie operacje na rejestrze
- RemoteToolsRegistry — obsługę błędów HTTP (bez prawdziwego serwera)
"""
import json
import pytest
from unittest.mock import patch, MagicMock

from core.schemas import WorkerRegistrationRequest, ToolExecutionRequest
from node.services.remote_tools_registry import RemoteToolsRegistry


# ─── Testy WorkerRegistrationRequest ─────────────────────────────────────────

def test_worker_registration_request_valid():
    req = WorkerRegistrationRequest(
        id="rpi5-worker",
        host="127.0.0.1",
        port=8001,
        model_name="qwen2.5:1.5b-instruct",
        priority=10
    )
    assert req.id == "rpi5-worker"
    assert req.host == "127.0.0.1"
    assert req.port == 8001
    assert req.model_name == "qwen2.5:1.5b-instruct"
    assert req.priority == 10


def test_tool_execution_request_defaults():
    req = ToolExecutionRequest(tool_name="get_current_time", arguments={})
    assert req.tool_name == "get_current_time"
    assert req.room is None


# ─── Testy logiki wyboru węzła ─────────────────────────────────────────────

def _build_registry(*workers: dict) -> dict[str, dict]:
    """Pomocnik: buduje słownik rejestru z listy węzłów."""
    return {w["id"]: w for w in workers}


def _pick_worker_from(registry: dict) -> dict | None:
    """Lokalny odpowiednik selekcji według najniższego priority (najwyższego priorytetu)."""
    if not registry:
        return None
    return min(registry.values(), key=lambda w: w.get("priority", 10))


def test_pick_worker_empty_registry():
    assert _pick_worker_from({}) is None


def test_pick_worker_single():
    registry = _build_registry({"id": "w1", "host": "127.0.0.1", "port": 8001, "priority": 10, "model_name": "q1.5b", "base_url": "http://127.0.0.1:8001"})
    assert _pick_worker_from(registry)["id"] == "w1"


def test_pick_worker_prefers_lower_priority_number():
    registry = _build_registry(
        {"id": "w-rpi", "host": "127.0.0.1", "port": 8001, "priority": 10, "model_name": "q1.5b", "base_url": "http://127.0.0.1:8001"},
        {"id": "w-gpu", "host": "192.168.0.10", "port": 8001, "priority": 0, "model_name": "q14b", "base_url": "http://192.168.0.10:8001"},
    )
    best = _pick_worker_from(registry)
    assert best["id"] == "w-gpu"


 


# ─── Testy RemoteToolsRegistry ────────────────────────────────────────────────

def test_remote_tools_registry_success():
    expected = json.dumps({"result": "success"}, ensure_ascii=False)
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.text = expected
    mock_response.raise_for_status = MagicMock()

    with patch("requests.Session.post", return_value=mock_response) as mock_post:
        registry = RemoteToolsRegistry("http://127.0.0.1:8000", "regis")
        result = registry.execute_tool("get_current_time", {})

    assert result == expected
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "v1/tools/execute" in call_kwargs[0][0]


def test_remote_tools_registry_connection_error():
    import requests as req_lib
    with patch("requests.Session.post", side_effect=req_lib.RequestException("timeout")):
        registry = RemoteToolsRegistry("http://127.0.0.1:8000", "regis")
        result = registry.execute_tool("get_current_time", {})

    data = json.loads(result)
    assert "error" in data
