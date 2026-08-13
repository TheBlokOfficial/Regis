import tempfile
from pathlib import Path
from typing import AsyncIterator, List
import pytest
from fastapi.testclient import TestClient

from server.agent import AgentEngine
from server.agent.backend import BaseLLMProvider, LLMMessage, LLMResponse
from server.agent.backend.registry import BackendRegistry
from server.agent.memory import MemoryManager
from server.network.gateway import create_gateway_app


class MockLLMProvider(BaseLLMProvider):
    """Mock Dostawca LLM na potrzeby szybkich i przewidywalnych testów jednostkowych API."""

    def __init__(self, model_name: str = "mock-model-v1") -> None:
        self._model = model_name

    async def generate(self, messages: List[LLMMessage]) -> LLMResponse:
        last_msg = messages[-1].content if messages else ""
        return LLMResponse(
            content=f"Echo: {last_msg}",
            model=self._model,
        )

    async def generate_stream(self, messages: List[LLMMessage]) -> AsyncIterator[str]:
        last_msg = messages[-1].content if messages else ""
        words = ["Echo:", last_msg]
        for word in words:
            yield f" {word}"

    async def check_health(self) -> bool:
        return True


@pytest.fixture
def test_client():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Usługi z osobnym katalogiem tymczasowym dla pamięci
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        mock_provider = MockLLMProvider()
        agent_engine = AgentEngine(
            llm_provider=mock_provider,
            memory_manager=memory_manager,
        )
        backend_registry = BackendRegistry(data_dir=tmp_path / "backends")

        app = create_gateway_app(
            agent_engine=agent_engine,
            event_bus=None,  # type: ignore
            backend_registry=backend_registry,
        )

        with TestClient(app) as client:
            yield client, memory_manager


def test_chat_sessions_endpoints(test_client):
    client, memory = test_client

    # 1. GET /api/chat/sessions (powinna zawierać domyślną sesję)
    res_list = client.get("/api/chat/sessions")
    assert res_list.status_code == 200
    data_list = res_list.json()
    assert "sessions" in data_list
    assert len(data_list["sessions"]) == 1
    assert data_list["sessions"][0]["session_id"] == "session_default"

    # 2. POST /api/chat/sessions (tworzenie nowej sesji)
    res_create = client.post("/api/chat/sessions", json={"title": "Testowa Nowa Sesja"})
    assert res_create.status_code == 201
    new_session_data = res_create.json()
    assert new_session_data["title"] == "Testowa Nowa Sesja"
    new_id = new_session_data["session_id"]
    assert new_id.startswith("session_")

    # Lista sesji po utworzeniu
    res_list2 = client.get("/api/chat/sessions")
    assert len(res_list2.json()["sessions"]) == 2


def test_chat_interaction_and_history(test_client):
    client, memory = test_client

    # 1. POST /api/chat (wysłanie pytania)
    res_chat = client.post(
        "/api/chat",
        json={
            "session_id": "session_default",
            "message": "Jaki jest Twój status?",
        },
    )
    assert res_chat.status_code == 200
    chat_data = res_chat.json()
    assert chat_data["session_id"] == "session_default"
    assert chat_data["message"]["role"] == "assistant"
    assert "Echo: Jaki jest Twój status?" in chat_data["message"]["content"]
    assert chat_data["model"] == "mock-model-v1"

    # 2. GET /api/chat/sessions/session_default/history
    res_hist = client.get("/api/chat/sessions/session_default/history")
    assert res_hist.status_code == 200
    hist_data = res_hist.json()
    assert len(hist_data["messages"]) == 2  # 1 User + 1 Assistant
    assert hist_data["messages"][0]["role"] == "user"
    assert hist_data["messages"][0]["content"] == "Jaki jest Twój status?"
    assert hist_data["messages"][1]["role"] == "assistant"


def test_chat_streaming(test_client):
    client, memory = test_client

    # POST /api/chat/stream
    res_stream = client.post(
        "/api/chat/stream",
        json={
            "session_id": "session_default",
            "message": "Cześć Strumień",
        },
    )
    assert res_stream.status_code == 200
    assert "text/event-stream" in res_stream.headers["content-type"]
    lines = res_stream.text.splitlines()

    # Sprawdzenie czy pojawiły się zdarzenia SSE
    data_lines = [line for line in lines if line.startswith("data:")]
    assert len(data_lines) >= 2
    assert "DONE" in data_lines[-1]


def test_cancel_chat_api(test_client):
    client, memory = test_client

    # POST /api/chat/cancel (dla niezajętej sesji)
    res_cancel = client.post(
        "/api/chat/cancel",
        json={"session_id": "session_default"},
    )
    assert res_cancel.status_code == 200
    cancel_data = res_cancel.json()
    assert cancel_data["success"] is False
    assert cancel_data["session_id"] == "session_default"

