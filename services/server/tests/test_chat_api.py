import tempfile
from pathlib import Path
from typing import AsyncIterator, List

import pytest
from fastapi.testclient import TestClient
from server.agent import AgentEngine
from server.agent.context_provider import ContextBuild
from server.agent.llm import BaseLLMProvider, LLMMessage, LLMResponse, ToolCallRequest, ToolDefinition, ToolResult
from server.agent.memory import MemoryManager
from server.agent.prompts import AgentDefaultPromptStore
from server.ai.llm.registry import BackendRegistry
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

    async def generate_stream(self, messages: List[LLMMessage], tools=None, **kwargs) -> AsyncIterator[str]:
        last_msg = messages[-1].content if messages else ""
        words = ["Echo:", last_msg]
        for word in words:
            yield f" {word}"

@pytest.fixture
def test_client():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Usługi z osobnym katalogiem tymczasowym dla pamięci
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        mock_provider = MockLLMProvider()
        prompt_store = AgentDefaultPromptStore(data_dir=tmp_path)
        agent_engine = AgentEngine(
            llm_provider=mock_provider,
            memory_manager=memory_manager,
            prompt_store=prompt_store,
        )
        backend_registry = BackendRegistry(data_dir=tmp_path / "backends")

        app = create_gateway_app(
            agent_engine=agent_engine,
            backend_registry=backend_registry,
            prompt_store=prompt_store,
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

    async def generate_stream(self, messages: List[LLMMessage], tools=None, **kwargs) -> AsyncIterator[str]:
        import asyncio
        words = ["Słowo1", "Słowo2", "Słowo3"]
        for word in words:
            await asyncio.sleep(0.05)
            yield f" {word}"

@pytest.mark.anyio
async def test_async_background_generation_and_status():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        slow_provider = SlowMockLLMProvider()
        engine = AgentEngine(llm_provider=slow_provider, memory_manager=memory_manager)
        backend_registry = BackendRegistry(data_dir=tmp_path / "backends")
        prompt_store = AgentDefaultPromptStore(data_dir=tmp_path)
        app = create_gateway_app(agent_engine=engine, backend_registry=backend_registry, prompt_store=prompt_store)

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


class FailingLLMProvider(BaseLLMProvider):
    """Rzuca wyjątek niosący 'wrażliwy' szczegół techniczny — symuluje surową odpowiedź
    błędu API dostawcy (np. treść HTTP 429 z wewnętrznym ID organizacji), która nie
    powinna nigdy trafić do treści widocznej dla użytkownika."""

    async def generate(self, messages: List[LLMMessage]) -> LLMResponse:
        raise RuntimeError("nie powinno być wołane w tym teście")

    async def generate_stream(self, messages: List[LLMMessage], tools=None, **kwargs) -> AsyncIterator[str]:
        raise RuntimeError(
            "Błąd API [https://api.groq.com/openai/v1] HTTP 429: "
            '{"error":{"message":"...","org":"org_supertajne_konto_id"}}'
        )
        yield  # pragma: no cover - nieosiągalne, ale czyni z tego async generator

@pytest.mark.anyio
async def test_llm_error_does_not_leak_raw_detail_to_user_facing_content():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        engine = AgentEngine(llm_provider=FailingLLMProvider(), memory_manager=memory_manager)

        with pytest.raises(RuntimeError) as exc_info:
            async for _ in engine.interact_stream(session_id="session_default", prompt="Zgaś światła"):
                pass

        # Wyjątek widziany przez wywołującego (HTTP stream/sync, WS głosowy) jest już ogólny.
        assert "org_supertajne_konto_id" not in str(exc_info.value)
        assert "Wystąpił błąd" in str(exc_info.value)

        # Historia sesji (to, co widzi użytkownik w Chat UI) też nie zawiera surowego szczegółu.
        history = memory_manager.get_history("session_default")
        assert len(history) == 2
        assert history[1].role == "assistant"
        assert history[1].metadata.get("is_error") is True
        assert "org_supertajne_konto_id" not in history[1].content
        assert "Wystąpił błąd" in history[1].content


@pytest.mark.anyio
async def test_disconnect_does_not_cancel_background_task():
    import asyncio
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        slow_provider = SlowMockLLMProvider()
        engine = AgentEngine(llm_provider=slow_provider, memory_manager=memory_manager)
        backend_registry = BackendRegistry(data_dir=tmp_path / "backends")
        prompt_store = AgentDefaultPromptStore(data_dir=tmp_path)
        create_gateway_app(agent_engine=engine, backend_registry=backend_registry, prompt_store=prompt_store)

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


def test_chat_send_is_fire_and_forget(test_client):
    """POST /api/v1/chat/send (uzywany dzis przez Web UI zamiast /chat/stream) odpala
    ture w tle i wraca natychmiast z 202, bez tresci odpowiedzi - mirror
    AgentEngine.start_interaction(), z ktorego dotad korzystala tylko satelita glosowa."""
    client, memory = test_client

    res = client.post(
        "/api/v1/chat/send",
        json={"session_id": "session_default", "message": "Wyslij i zapomnij"},
    )
    assert res.status_code == 202
    assert res.json() == {"success": True, "session_id": "session_default"}

    # Odpowiedz przychodzi asynchronicznie - TestClient jest synchroniczny, wiec do czasu
    # kolejnego zadania petla w tle miala juz szanse dokonczyc (mock LLM jest natychmiastowy).
    history = client.get("/api/v1/chat/sessions/session_default/history").json()
    assert any(m["role"] == "user" and m["content"] == "Wyslij i zapomnij" for m in history["messages"])


def test_chat_send_rejects_busy_session():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        slow_provider = SlowMockLLMProvider()
        engine = AgentEngine(llm_provider=slow_provider, memory_manager=memory_manager)
        backend_registry = BackendRegistry(data_dir=tmp_path / "backends")
        prompt_store = AgentDefaultPromptStore(data_dir=tmp_path)
        app = create_gateway_app(agent_engine=engine, backend_registry=backend_registry, prompt_store=prompt_store)

        with TestClient(app) as client:
            first = client.post("/api/v1/chat/send", json={"session_id": "session_default", "message": "Pierwsza"})
            assert first.status_code == 202

            second = client.post("/api/v1/chat/send", json={"session_id": "session_default", "message": "Druga"})
            assert second.status_code == 409


@pytest.mark.anyio
async def test_watch_session_forwards_user_message_and_does_not_terminate():
    """`watch_session()` to pasywna obserwacja uzywana przez Web UI (`GET .../watch`) -
    w odroznieniu od `interact_stream()` powinna (1) przekazac CHAT_USER_MESSAGE (dotad
    zadne zdarzenie nie nioslo tresci pytania uzytkownika poza pamiecia sesji) i (2) NIE
    konczyc sie samoistnie na 'done' - to obserwator (SSE) decyduje, kiedy przestac."""
    import asyncio

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        engine = AgentEngine(llm_provider=MockLLMProvider(), memory_manager=memory_manager)

        watcher = engine.watch_session("session_default")
        first_task = asyncio.ensure_future(anext(watcher))
        # Oddajemy sterowanie petli zdarzen, zeby generator zdazyl wykonac synchroniczna
        # czesc ciala (subskrypcje w EventBus) zanim odpalimy ture - inaczej start_interaction
        # moglby opublikowac CHAT_USER_MESSAGE, zanim ktokolwiek go subskrybuje.
        await asyncio.sleep(0)
        engine.start_interaction(session_id="session_default", prompt="Halo?")

        first = await first_task
        assert first.type == "user_message"
        assert first.payload["content"] == "Halo?"

        types = [first.type]
        async with asyncio.timeout(2.0):
            while types[-1] != "done":
                event = await anext(watcher)
                types.append(event.type)

        assert "chunk" in types
        assert types[-1] == "done"
        # Kluczowe: mimo 'done' generator NIE jest zamkniety samoistnie - w odroznieniu od
        # interact_stream (ktore po 'done' konczy iteracje), watch_session nigdy sam sie nie
        # konczy — to obserwator (SSE/klient) decyduje, kiedy przestac czytac.
        assert watcher.ag_frame is not None

        await watcher.aclose()


class SingleToolWorld:
    """Minimalny `WorldInterface` z jednym zawsze-dostępnym narzędziem — używany
    wyłącznie do odtworzenia scenariusza regresyjnego niżej (błąd PO co najmniej
    jednym wywołaniu narzędzia)."""

    async def build(self, sender_id=None) -> ContextBuild:
        del sender_id
        tool_def = ToolDefinition(name="noop_tool", description="test", parameters={"type": "object", "properties": {}})

        async def _dispatch(name: str, arguments: dict) -> ToolResult:
            del name, arguments
            return ToolResult(is_error=False, content="ok")

        return ContextBuild(tool_definitions=[tool_def], system_prompt=None, turn_context=None, dispatch=_dispatch)


class TextThenToolThenFailingProvider(BaseLLMProvider):
    """Emituje trochę tekstu, potem wywołanie narzędzia; NASTĘPNE wywołanie (po
    otrzymaniu wyniku narzędzia) rzuca wyjątek — odtwarza dokładnie scenariusz buga:
    bufor tekstu jest niepusty w momencie błędu."""

    def __init__(self) -> None:
        self._call_count = 0

    async def generate(self, messages):
        raise NotImplementedError

    async def generate_stream(self, messages, tools=None, **kwargs):
        self._call_count += 1
        if self._call_count == 1:
            yield "Analizuję sytuację. "
            yield ToolCallRequest(id="call_1", name="noop_tool", arguments={})
        else:
            raise RuntimeError("Błąd API dostawcy - szczegół techniczny")

@pytest.mark.anyio
async def test_error_after_tool_call_preserves_partial_text_prefix():
    """Regresja: błąd występujący PO co najmniej jednym wywołaniu narzędzia musi
    zachować już-wygenerowany tekst jako prefiks utrwalonej treści (mirror gałęzi
    CancelledError) — inaczej `text_offset` zapisanych kroków wskazuje w pustkę po
    całkowitej podmianie treści na komunikat błędu, co przy replayu z historii
    (`chat.js::buildSegments`) odwracało kolejność: krok narzędzia renderował się PO
    komunikacie błędu zamiast przed nim (zaobserwowane na żywo przez użytkownika)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory_manager = MemoryManager(data_dir=tmp_path / "sessions")
        provider = TextThenToolThenFailingProvider()
        engine = AgentEngine(llm_provider=provider, memory_manager=memory_manager, world=SingleToolWorld())

        # Wołamy `_generate_in_background` bezpośrednio (nie `interact_stream`/
        # `start_interaction`) — to jedyna jednostka kodu istotna dla tej regresji
        # (zachowanie gałęzi `except Exception`), a ominięcie fire-and-forget
        # `asyncio.create_task` unika sztucznego "Task exception was never retrieved"
        # (anyio traktuje nieodebrany wyjątek zadania w tle jako błąd testu, niezależnie
        # od tego, że produkcyjnie jest on i tak w pełni obsłużony przez CHAT_ERROR/logi).
        with pytest.raises(RuntimeError):
            await engine._generate_in_background(session_id="session_default", prompt="Test")

        history = memory_manager.get_history("session_default")
        assert history[1].role == "assistant"
        content = history[1].content
        assert content.startswith("Analizuję sytuację. ")
        assert "Wystąpił błąd" in content

        tool_call_step = next(s for s in history[1].metadata["steps"] if s["type"] == "tool_call")
        # Offset musi nadal wskazywać na koniec RZECZYWIŚCIE wygenerowanego tekstu, nie na
        # końcowy (przycięty) offset zupełnie innej, podmienionej treści błędu.
        assert tool_call_step["text_offset"] == len("Analizuję sytuację. ")
        assert content[: tool_call_step["text_offset"]] == "Analizuję sytuację. "
