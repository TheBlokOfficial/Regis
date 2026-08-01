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
from node.remote_tools_registry import RemoteToolsRegistry


# ─── Testy WorkerRegistrationRequest ─────────────────────────────────────────

def test_worker_registration_request_valid():
    req = WorkerRegistrationRequest(
        id="rpi5-worker",
        host="127.0.0.1",
        port=8001,
        model_name="qwen2.5:1.5b-instruct",
        tier="butler"
    )
    assert req.id == "rpi5-worker"
    assert req.host == "127.0.0.1"
    assert req.port == 8001
    assert req.model_name == "qwen2.5:1.5b-instruct"
    assert req.tier == "butler"


def test_tool_execution_request_defaults():
    req = ToolExecutionRequest(tool_name="get_current_time", arguments={})
    assert req.tier == "regis"


def test_tool_execution_request_custom_tier():
    req = ToolExecutionRequest(
        tool_name="execute_ha_action",
        arguments={"action": "turn_on", "entity_id": "light.salon"},
        tier="regis"
    )
    assert req.tier == "regis"


# ─── Testy logiki wyboru węzła ─────────────────────────────────────────────

def _build_registry(*workers: dict) -> dict[str, dict]:
    """Pomocnik: buduje słownik rejestru z listy węzłów."""
    return {w["id"]: w for w in workers}


def _pick_worker_from(registry: dict) -> dict | None:
    """Lokalny odpowiednik _pick_worker z controller/main.py."""
    TIER_PRIORITY = {"regis": 2, "butler": 1}
    if not registry:
        return None
    return max(registry.values(), key=lambda w: TIER_PRIORITY.get(w["tier"], 0))


def test_pick_worker_empty_registry():
    assert _pick_worker_from({}) is None


def test_pick_worker_single():
    registry = _build_registry({"id": "w1", "host": "127.0.0.1", "port": 8001, "tier": "butler", "model_name": "q1.5b", "base_url": "http://127.0.0.1:8001"})
    assert _pick_worker_from(registry)["id"] == "w1"


def test_pick_worker_prefers_higher_tier():
    registry = _build_registry(
        {"id": "w-butler", "host": "127.0.0.1", "port": 8001, "tier": "butler", "model_name": "q1.5b", "base_url": "http://127.0.0.1:8001"},
        {"id": "w-regis",  "host": "192.168.0.10", "port": 8001, "tier": "regis",  "model_name": "q14b",  "base_url": "http://192.168.0.10:8001"},
    )
    best = _pick_worker_from(registry)
    assert best["id"] == "w-regis"


 


# ─── Testy RemoteToolsRegistry ────────────────────────────────────────────────

def test_remote_tools_registry_success():
    expected = json.dumps({"result": "success"}, ensure_ascii=False)
    mock_response = MagicMock()
    mock_response.ok = True
    mock_response.text = expected
    mock_response.raise_for_status = MagicMock()

    with patch("requests.post", return_value=mock_response) as mock_post:
        registry = RemoteToolsRegistry("http://127.0.0.1:8000", "regis")
        result = registry.execute_tool("get_current_time", {})

    assert result == expected
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert "v1/tools/execute" in call_kwargs[0][0]


def test_remote_tools_registry_connection_error():
    import requests as req_lib
    with patch("requests.post", side_effect=req_lib.RequestException("timeout")):
        registry = RemoteToolsRegistry("http://127.0.0.1:8000", "regis")
        result = registry.execute_tool("get_current_time", {})

    data = json.loads(result)
    assert "error" in data
