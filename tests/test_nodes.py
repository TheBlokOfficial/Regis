import pytest
from fastapi.testclient import TestClient

from controller.app import app
import controller.registry as registry

client = TestClient(app)


def test_node_registration_and_unregistration():
    registry.node_registry.clear()

    payload = {
        "id": "test-rtx-5070",
        "name": "RTX-5070-PC",
        "host": "192.168.0.68",
        "port": 8099,
        "services": {
            "worker": {
                "model_name": "qwen3.5:9b",
                "priority": 100,
            },
            "satellite": {
                "room": "pracownia_glowna",
                "node_type": "desktop",
                "capabilities": ["audio_input", "tts_output", "wakeword"],
                "wakeword_local": True,
            }
        }
    }

    # 1. Registration
    response = client.post("/v1/nodes/register", json=payload)
    assert response.status_code == 200
    res = response.json()
    assert res["status"] == "registered"
    assert res["id"] == "test-rtx-5070"

    assert "test-rtx-5070" in registry.node_registry
    node = registry.node_registry["test-rtx-5070"]
    assert "worker" in node["services"]
    assert "satellite" in node["services"]
    assert node["services"]["worker"]["model_name"] == "qwen3.5:9b"

    # 2. Getters
    workers = registry.get_worker_nodes()
    assert any(w["id"] == "test-rtx-5070" and w["model_name"] == "qwen3.5:9b" for w in workers)

    satellites = registry.get_satellite_nodes()
    assert any(s["id"] == "test-rtx-5070" and s["room"] == "pracownia_glowna" for s in satellites)

    # 3. Supported models & Config GET/POST
    models_res = client.get("/v1/nodes/supported_models")
    assert models_res.status_code == 200
    assert any(m["id"] == "qwen3.5:9b" for m in models_res.json()["models"])

    cfg_res = client.get("/v1/nodes/test-rtx-5070/config")
    assert cfg_res.status_code == 200

    # 4. Unregistration
    del_response = client.delete("/v1/nodes/test-rtx-5070")
    assert del_response.status_code == 200
    assert del_response.json() == {"status": "ok"}
    assert "test-rtx-5070" not in registry.node_registry
