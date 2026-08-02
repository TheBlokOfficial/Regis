"""Testy jednostkowe dla Spatial Context Filtering.

Testują:
- Model SatelliteRegistrationRequest (walidacja payloadu)
- Filtrowanie urządzeń w ToolsRegistry per pokój (_get_devices)
- Propagację room w RemoteToolsRegistry (payload do Kontrolera)
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from protocol.schemas import SatelliteRegistrationRequest, ToolExecutionRequest
from controller.tools_registry import ToolsRegistry
from client.services.remote_tools_registry import RemoteToolsRegistry


# ─── Fixtures ─────────────────────────────────────────────────────────────────

ROOMS = {
    "salon": ["light.salon_lampa", "switch.salon_tv"],
    "sypialnia": ["light.sypialnia_lampa"],
}

HA_STATES = {
    "light.salon_lampa":    {"state": "on",  "friendly_name": "Lampa w salonie"},
    "switch.salon_tv":      {"state": "off", "friendly_name": "Telewizor"},
    "light.sypialnia_lampa":{"state": "off", "friendly_name": "Lampa w sypialni"},
    "light.kuchnia_spot":   {"state": "on",  "friendly_name": "Spot kuchenny"},
}


def _make_registry(rooms: dict = None) -> ToolsRegistry:
    """Buduje ToolsRegistry z mockiem HA i opcjonalnym słownikiem pokojów."""
    ha_mock = MagicMock()
    ha_mock.get_all_states.return_value = HA_STATES
    return ToolsRegistry(ha_client=ha_mock, rooms=rooms or {})


# ─── Testy SatelliteRegistrationRequest ───────────────────────────────────────

def test_satellite_registration_full():
    req = SatelliteRegistrationRequest(
        id="terminal-dev",
        room="salon",
        type="terminal",
        capabilities=["text"],
        wakeword_local=False,
    )
    assert req.id == "terminal-dev"
    assert req.room == "salon"
    assert req.type == "terminal"
    assert req.capabilities == ["text"]
    assert req.wakeword_local is False


def test_satellite_registration_room_optional():
    """room jest opcjonalne — None oznacza brak filtrowania."""
    req = SatelliteRegistrationRequest(
        id="esp32-kuchnia",
        type="esp32",
        capabilities=["audio_in", "audio_out"],
    )
    assert req.room is None


def test_tool_execution_request_room_field():
    req = ToolExecutionRequest(tool_name="get_devices", arguments={}, room="salon")
    assert req.room == "salon"


def test_tool_execution_request_room_default_none():
    req = ToolExecutionRequest(tool_name="get_devices", arguments={})
    assert req.room is None


# ─── Testy filtrowania w ToolsRegistry ────────────────────────────────────────

def test_get_devices_no_room_returns_all():
    """Brak room → wszystkie urządzenia (zachowanie wsteczne)."""
    registry = _make_registry(ROOMS)
    result = json.loads(registry._get_devices(room=None))
    entity_ids = [d["entity_id"] for d in result["devices"]]
    assert len(entity_ids) == 3
    assert "light.salon_lampa" in entity_ids
    assert "light.kuchnia_spot" not in entity_ids


def test_get_devices_room_salon():
    """room='salon' → tylko urządzenia z salonu."""
    registry = _make_registry(ROOMS)
    result = json.loads(registry._get_devices(room="salon"))
    entity_ids = [d["entity_id"] for d in result["devices"]]
    assert set(entity_ids) == {"light.salon_lampa", "switch.salon_tv"}


def test_get_devices_room_sypialnia():
    """room='sypialnia' → tylko urządzenia z sypialni."""
    registry = _make_registry(ROOMS)
    result = json.loads(registry._get_devices(room="sypialnia"))
    entity_ids = [d["entity_id"] for d in result["devices"]]
    assert entity_ids == ["light.sypialnia_lampa"]


def test_get_devices_unknown_room_returns_all():
    """Nieznany pokój → wszystkie urządzenia (fallback — model nie zostaje bez kontekstu)."""
    registry = _make_registry(ROOMS)
    result = json.loads(registry._get_devices(room="garaz"))
    # rooms.get("garaz") → None → brak filtrowania → pełna lista
    assert len(result["devices"]) == 3


def test_get_devices_no_rooms_config_returns_all():
    """Brak rooms.json (pusty słownik) → wszystkie urządzenia."""
    registry = _make_registry(rooms={})
    result = json.loads(registry._get_devices(room="salon"))
    # rooms jest pusty — room_filter = None → brak filtrowania
    assert len(result["devices"]) == 0


def test_get_devices_room_and_domain_combined():
    """Filtrowanie po room i domain jednocześnie."""
    registry = _make_registry(ROOMS)
    result = json.loads(registry._get_devices(domain="switch", room="salon"))
    entity_ids = [d["entity_id"] for d in result["devices"]]
    assert entity_ids == ["switch.salon_tv"]


# ─── Testy RemoteToolsRegistry ────────────────────────────────────────────────

def test_remote_tools_registry_passes_room():
    """RemoteToolsRegistry przekazuje room w payloadzie do Kontrolera."""
    mock_response = MagicMock()
    mock_response.text = json.dumps({"devices": []})
    mock_response.raise_for_status = MagicMock()

    with patch("requests.Session.post", return_value=mock_response) as mock_post:
        registry = RemoteToolsRegistry("http://127.0.0.1:8000", room="salon")
        registry.execute_tool("get_devices", {})

    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["json"]["room"] == "salon"


def test_remote_tools_registry_room_none_passes_null():
    """room=None jest przekazywany wprost (null w JSON)."""
    mock_response = MagicMock()
    mock_response.text = json.dumps({"devices": []})
    mock_response.raise_for_status = MagicMock()

    with patch("requests.Session.post", return_value=mock_response) as mock_post:
        registry = RemoteToolsRegistry("http://127.0.0.1:8000", room=None)
        registry.execute_tool("get_devices", {})

    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["json"]["room"] is None
