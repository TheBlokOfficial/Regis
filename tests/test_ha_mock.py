import pytest
import os
from controller.integrations.ha_mock import HomeAssistantMock

@pytest.fixture
def mock_client(tmp_path):
    # Overwrite the state file to use a temporary one
    from controller.integrations import ha_mock
    original_state_file = ha_mock.STATE_FILE
    test_state_file = tmp_path / "test_ha_state.json"
    ha_mock.STATE_FILE = str(test_state_file)
    
    client = HomeAssistantMock()
    yield client
    
    # Restore original path
    ha_mock.STATE_FILE = original_state_file

def test_mock_get_all_states(mock_client):
    states = mock_client.get_all_states()
    assert "light.salon" in states
    assert states["light.salon"]["state"] == "off"

def test_mock_execute_action(mock_client):
    # Włączamy salon
    success = mock_client.execute_action("turn_on", "light.salon")
    assert success is True
    
    # Sprawdzamy czy stan się zmienił
    states = mock_client.get_all_states()
    assert states["light.salon"]["state"] == "on"

def test_mock_execute_unknown_action(mock_client):
    success = mock_client.execute_action("fly", "light.salon")
    assert success is False
