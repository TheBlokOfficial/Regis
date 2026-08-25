"""Bramka rejestracji — każdy klient wchodzi do systemu tą samą drogą.

Nie jest to mechanizm bezpieczeństwa (sieć jest zaufana, patrz `docs/manifest.md`),
tylko konsekwencja: klient, którego nie ma w `World`, nie odpala tury — niezależnie
od tego, czy przyszedł REST-em (przeglądarka) czy WS-em (satelita). Wcześniej żadne
z tych wejść niczego nie sprawdzało.
"""

from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.agent import AgentEngine
from server.agent.memory import MemoryManager
from server.agent.prompts import AgentDefaultPromptStore
from server.ai.llm.registry import BackendRegistry
from server.ai.stt import MockSTTProvider
from server.ai.tts import MockTTSProvider
from server.ai.wakeword import ThresholdEnergyWakeWordDetector
from server.config import Settings
from server.network.gateway import create_gateway_app
from server.ports.llm import BaseLLMProvider, LLMMessage
from server.voice.gateway import create_voice_router
from shared import EventBus

REGISTERED = "znany_klient"
UNKNOWN = "obcy_klient"


class _EchoProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self._model = "mock"

    async def generate_stream(self, messages: List[LLMMessage], tools=None, **kwargs: Any) -> AsyncIterator[str]:
        del messages, tools, kwargs
        yield "ok"

async def _is_registered(sender_id: str) -> bool:
    return sender_id == REGISTERED


@pytest.fixture
def rest_client():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        prompt_store = AgentDefaultPromptStore(data_dir=tmp_path)
        app = create_gateway_app(
            agent_engine=AgentEngine(
                llm_provider=_EchoProvider(),
                memory_manager=MemoryManager(data_dir=tmp_path / "sessions"),
                prompt_store=prompt_store,
            ),
            backend_registry=BackendRegistry(data_dir=tmp_path / "backends"),
            prompt_store=prompt_store,
            is_registered=_is_registered,
        )
        with TestClient(app) as client:
            yield client


def test_unregistered_sender_cannot_start_a_turn(rest_client: TestClient) -> None:
    response = rest_client.post(
        "/api/v1/chat/send", json={"session_id": "czat_1", "message": "cześć", "sender_id": UNKNOWN}
    )
    assert response.status_code == 403
    assert UNKNOWN in response.json()["detail"]


def test_registered_sender_passes_the_gate(rest_client: TestClient) -> None:
    response = rest_client.post(
        "/api/v1/chat/send", json={"session_id": "czat_1", "message": "cześć", "sender_id": REGISTERED}
    )
    assert response.status_code == 202


def test_request_without_sender_id_is_not_gated(rest_client: TestClient) -> None:
    """Wywołania headless (skrypty, cron) nie udają żadnego klienta i nie mają czego
    rejestrować — bramka ich nie dotyczy."""
    response = rest_client.post("/api/v1/chat/send", json={"session_id": "czat_1", "message": "cześć"})
    assert response.status_code == 202


class _FakeAgentEngine:
    def __init__(self) -> None:
        self.event_bus = EventBus()
        self.started: list[str] = []

    def start_interaction(self, **kwargs: Any) -> None:
        self.started.append(str(kwargs.get("sender_id")))


def _voice_app(agent_engine: _FakeAgentEngine) -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_voice_router(
            agent_engine=agent_engine,
            wakeword_detector_factory=ThresholdEnergyWakeWordDetector,
            stt_provider=MockSTTProvider(),
            tts_provider=MockTTSProvider(),
            connected_sender_ids=set(),
            settings_loader=Settings,
            sender_states={},
            pending_capabilities={},
            is_registered=_is_registered,
        ),
        prefix="/ws",
    )
    return app


# `ThresholdEnergyWakeWordDetector` (placeholder używany w testach) wyzwala się po
# trzech kolejnych ramkach o amplitudzie >= 2000 — cisza nie wystarczy, a bez wykrycia
# wake-worda `utterance_end` jest po cichu ignorowane i sesja nie ruszy z miejsca.
_LOUD_FRAME = struct.pack("<h", 6000) * 160


def _drain_until_error(ws, max_frames: int = 6) -> dict[str, Any] | None:
    """Satelita dostaje po drodze `client_config`, `wake_detected` i `play_stop_tone`;
    interesuje nas dopiero ramka `error`."""
    for _ in range(max_frames):
        frame = json.loads(ws.receive_text())
        if frame.get("type") == "error":
            return frame
    return None


def test_unregistered_satellite_may_connect_but_not_start_a_turn() -> None:
    """Połączyć się wolno każdemu — inaczej nowa satelita nigdy nie pojawiłaby się na
    liście "Oczekujący" i nie dałoby się jej zatwierdzić. Turę odpala dopiero zatwierdzona."""
    agent_engine = _FakeAgentEngine()
    with TestClient(_voice_app(agent_engine)) as client:
        with client.websocket_connect(f"/ws/voice/{UNKNOWN}") as ws:
            ws.send_text(json.dumps({"type": "hello", "capabilities": ["mic", "speaker"]}))
            for _ in range(3):
                ws.send_bytes(_LOUD_FRAME)
            ws.send_text(json.dumps({"type": "utterance_end"}))

            error_frame = _drain_until_error(ws)

    assert error_frame is not None
    assert "zarejestrowany" in error_frame["detail"]
    assert agent_engine.started == []


def test_registered_satellite_starts_a_turn() -> None:
    """Kontrola pozytywna — bez niej test wyżej przechodziłby też wtedy, gdyby tura
    nie odpalała się nigdy, z zupełnie innego powodu."""
    agent_engine = _FakeAgentEngine()
    with TestClient(_voice_app(agent_engine)) as client:
        with client.websocket_connect(f"/ws/voice/{REGISTERED}") as ws:
            ws.send_text(json.dumps({"type": "hello", "capabilities": ["mic", "speaker"]}))
            for _ in range(3):
                ws.send_bytes(_LOUD_FRAME)
            # 3 ramki wyzwalające wake-word są zużyte przez sam detektor (nic nie trafia
            # jeszcze do bufora wypowiedzi) — bez dodatkowej "mowy" po wykryciu nagranie
            # miałoby 0 bajtów (peak_amplitude(b"") == 0) i zostałoby odrzucone przez
            # serwerową bramkę `Settings.vad_amplitude_threshold`, zanim tura w ogóle ruszy.
            ws.send_bytes(_LOUD_FRAME * 80)
            ws.send_text(json.dumps({"type": "utterance_end"}))
            # `tts_start` przychodzi dopiero po realnej turze; tu wystarczy, że doszliśmy
            # do syntezy Mock — czyli bramka przepuściła i STT/kernel zostały odpalone.
            for _ in range(6):
                if json.loads(ws.receive_text()).get("type") == "play_stop_tone":
                    break

    assert agent_engine.started == [REGISTERED]
