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

    # 1. GET /api/v1/chat/sessions (powinna zawierać domyślną sesję)
    res_list = client.get("/api/v1/chat/sessions")
    assert res_list.status_code == 200
    data_list = res_list.json()
    assert "sessions" in data_list
    assert len(data_list["sessions"]) == 1
    assert data_list["sessions"][0]["session_id"] == "session_default"

    # 2. POST /api/v1/chat/sessions (tworzenie nowej sesji)
    res_create = client.post("/api/v1/chat/sessions", json={"title": "Testowa Nowa Sesja"})
    assert res_create.status_code == 201
    new_session_data = res_create.json()
    assert new_session_data["title"] == "Testowa Nowa Sesja"
    new_id = new_session_data["session_id"]
    assert new_id.startswith("session_")

    # Lista sesji po utworzeniu
    res_list2 = client.get("/api/v1/chat/sessions")
    assert len(res_list2.json()["sessions"]) == 2


def test_chat_interaction_and_history(test_client):
    client, memory = test_client

    # 1. POST /api/v1/chat (wysłanie pytania)
    res_chat = client.post(
        "/api/v1/chat",
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

    # 2. GET /api/v1/chat/sessions/session_default/history
    res_hist = client.get("/api/v1/chat/sessions/session_default/history")
    assert res_hist.status_code == 200
    hist_data = res_hist.json()
    assert len(hist_data["messages"]) == 2  # 1 User + 1 Assistant
    assert hist_data["messages"][0]["role"] == "user"
    assert hist_data["messages"][0]["content"] == "Jaki jest Twój status?"
    assert hist_data["messages"][1]["role"] == "assistant"


def test_chat_streaming(test_client):
    client, memory = test_client

    # POST /api/v1/chat/stream
    res_stream = client.post(
        "/api/v1/chat/stream",
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

    # POST /api/v1/chat/cancel (dla niezajętej sesji)
    res_cancel = client.post(
        "/api/v1/chat/cancel",
        json={"session_id": "session_default"},
    )
    assert res_cancel.status_code == 200
    cancel_data = res_cancel.json()
    assert cancel_data["success"] is False
    assert cancel_data["session_id"] == "session_default"


class SlowMockLLMProvider(BaseLLMProvider):
    """Mock z opóźnieniem do testowania stanu generacji w tle."""

    async def generate(self, messages: List[LLMMessage]) -> LLMResponse:
        return LLMResponse(content="Slow response", model="slow-mock")

    async def generate_stream(self, messages: List[LLMMessage]) -> AsyncIterator[str]:
        import asyncio
        words = ["Słowo1", "Słowo2", "Słowo3"]
        for word in words:
            await asyncio.sleep(0.05)
            yield f" {word}"

    async def check_health(self) -> bool:
        return True


@pytest.mark.anyio
async def test_async_background_generation_and_status():
    import asyncio
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        slow_provider = SlowMockLLMProvider()
        engine = AgentEngine(llm_provider=slow_provider, memory_manager=memory_manager)
        backend_registry = BackendRegistry(data_dir=tmp_path / "backends")
        app = create_gateway_app(agent_engine=engine, event_bus=None, backend_registry=backend_registry)

        with TestClient(app) as client:
            # Rozpoczynamy generowanie strumieniowe w tle przez engine
            stream_gen = engine.interact_stream(session_id="session_default", prompt="Długie pytanie")
            
            # Pobieramy pierwszy element (co rozpoczyna zadanie w tle)
            token = await anext(stream_gen)
            assert token is not None
            assert engine.is_session_busy("session_default") is True

            # Sprawdzamy GET history gdy generowanie trwa
            res_hist = client.get("/api/v1/chat/sessions/session_default/history")
            assert res_hist.status_code == 200
            data_hist = res_hist.json()
            assert data_hist["is_generating"] is True
            # Historia powinna mieć co najmniej wiadomość użytkownika oraz częściową odpowiedź asystenta
            assert len(data_hist["messages"]) >= 2
            partial_msg = data_hist["messages"][-1]
            assert partial_msg["role"] == "assistant"
            assert partial_msg["metadata"].get("is_partial") is True

            # Sprawdzamy listę sesji
            res_list = client.get("/api/v1/chat/sessions")
            assert res_list.status_code == 200
            sessions_data = res_list.json()["sessions"]
            default_sess = next(s for s in sessions_data if s["session_id"] == "session_default")
            assert default_sess["is_generating"] is True

            # Dokańczamy pobieranie strumienia
            async for _ in stream_gen:
                pass

            # Po zakończeniu sesja nie jest już zajęta
            assert engine.is_session_busy("session_default") is False

            # Sprawdzamy ponownie historię po zakończeniu
            res_hist_done = client.get("/api/v1/chat/sessions/session_default/history")
            assert res_hist_done.json()["is_generating"] is False


@pytest.mark.anyio
async def test_disconnect_does_not_cancel_background_task():
    import asyncio
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        slow_provider = SlowMockLLMProvider()
        engine = AgentEngine(llm_provider=slow_provider, memory_manager=memory_manager)
        backend_registry = BackendRegistry(data_dir=tmp_path / "backends")
        app = create_gateway_app(agent_engine=engine, event_bus=None, backend_registry=backend_registry)

        # 1. Rozpoczynamy interakcję strumieniową
        stream_gen = engine.interact_stream(session_id="session_default", prompt="Test rozłączenia klienta")
        first_token = await anext(stream_gen)
        assert first_token is not None
        assert engine.is_session_busy("session_default") is True

        # 2. Symulujemy rozłączenie klienta SSE (anulowanie korutyny strumieniowej)
        await stream_gen.aclose()

        # Zadanie w tle POWINNO nadal trwać bez przerywania
        assert engine.is_session_busy("session_default") is True

        # ODczekujemy chwilę, by zadanie w tle mogło zakończyć swoją pracę
        await asyncio.sleep(0.3)

        # Po zakończeniu zadanie powinno się zwolnić, a odpowiedź utrwalić w historii
        assert engine.is_session_busy("session_default") is False
        history = memory_manager.get_history("session_default")
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[1].role == "assistant"
        assert "[Przerwano]" not in history[1].content
        assert "Słowo1 Słowo2 Słowo3" in history[1].content



