"""Testy `GET/PUT /api/v1/voice/client-config` (`voice/routes.py`) oraz regresja
live-reload progu wake-worda (`main.py::_build_wakeword_detector_factory`)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from server.config import Settings
from server.main import _build_wakeword_detector_factory
from server.ports.stt import BaseSTTProvider
from server.ports.tts import BaseTTSProvider
from server.voice.routes import create_voice_status_router
from shared import ConfigStore, EventBus


def _make_client(tmp_path: Path) -> tuple[TestClient, ConfigStore[Settings]]:
    config_store = ConfigStore(Settings, tmp_path / "settings.json")
    app = FastAPI()
    router = create_voice_status_router(
        stt_provider=None,  # nieużywane przez ten endpoint
        tts_provider=None,
        wakeword_detector_class_name="OnnxWakeWordDetector",
        connected_sender_ids=set(),
        config_store=config_store,
        sender_states={},
        event_bus=EventBus(),
        pending_capabilities={},
    )
    app.include_router(router, prefix="/api/v1/voice")
    return TestClient(app), config_store


def test_get_client_config_returns_defaults(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path)
    res = client.get("/api/v1/voice/client-config")
    assert res.status_code == 200
    data = res.json()
    assert data == {
        "wakeword_threshold": 0.65,
        "vad_silence_duration_ms": 1500.0,
        "vad_amplitude_threshold": 500,
    }


def test_put_client_config_persists_only_targeted_fields(tmp_path: Path) -> None:
    client, config_store = _make_client(tmp_path)

    res = client.put(
        "/api/v1/voice/client-config",
        json={"wakeword_threshold": 0.42, "vad_silence_duration_ms": 900.0, "vad_amplitude_threshold": 300},
    )
    assert res.status_code == 200
    assert res.json() == {
        "wakeword_threshold": 0.42,
        "vad_silence_duration_ms": 900.0,
        "vad_amplitude_threshold": 300,
    }

    # Pola niepowiązane (port, host, ...) nietknięte przez PUT.
    persisted = config_store.load()
    assert persisted.wakeword_threshold == 0.42
    assert persisted.vad_silence_duration_ms == 900.0
    assert persisted.vad_amplitude_threshold == 300
    assert persisted.port == Settings().port
    assert persisted.host == Settings().host

    # GET odzwierciedla zapisaną zmianę.
    res_get = client.get("/api/v1/voice/client-config")
    assert res_get.json()["wakeword_threshold"] == 0.42


def test_wakeword_threshold_reloads_without_restart(tmp_path: Path, monkeypatch) -> None:
    """Regresja: `_build_wakeword_detector_factory` dawniej zamykał `threshold` w
    closure przy starcie procesu — zmiana configu między dwoma wywołaniami `factory()`
    musi dać różny próg, bez restartu serwera (ten sam wzorzec co STT/TTS/LLM router)."""
    config_store = ConfigStore(Settings, tmp_path / "settings.json")
    model_path = tmp_path / "fake_model.onnx"
    model_path.write_bytes(b"")  # tylko istnienie pliku jest sprawdzane przed OnnxWakeWordDetector

    settings = Settings(wakeword_model_path=str(model_path), wakeword_threshold=0.3)
    monkeypatch.setattr("server.main.load_settings", lambda: config_store.load())
    monkeypatch.setattr("server.main.get_service_root", lambda _f: tmp_path)
    config_store.save(settings)

    class FakeOnnxWakeWordDetector:
        def __init__(self, model_path, threshold):
            self.threshold = threshold

    monkeypatch.setattr("server.main.OnnxWakeWordDetector", FakeOnnxWakeWordDetector)

    factory, _ = _build_wakeword_detector_factory(settings)

    first = factory()
    assert first.threshold == 0.3

    config_store.save(settings.model_copy(update={"wakeword_threshold": 0.8}))
    second = factory()
    assert second.threshold == 0.8


# --------------------------------------------------------------------------
# GET /status — `is_production_ready` musi wykrywać TAKŻE placeholder wake-worda
# --------------------------------------------------------------------------


class _RealisticSTT(BaseSTTProvider):
    """Nazwa klasy bez prefiksu `Mock` — inaczej test nie izolowałby zmiennej,
    którą bada (sam wake-word)."""

    async def transcribe(self, pcm_audio: bytes) -> str:
        return ""


class _RealisticTTS(BaseTTSProvider):
    async def synthesize_stream(self, text: str):
        del text
        return
        yield b""  # nieosiągalne — czyni funkcję generatorem; provider tu nigdy nie syntezuje


def _status_for_detector(tmp_path: Path, detector_name: str) -> dict:
    app = FastAPI()
    app.include_router(
        create_voice_status_router(
            stt_provider=_RealisticSTT(),
            tts_provider=_RealisticTTS(),
            wakeword_detector_class_name=detector_name,
            connected_sender_ids=set(),
            config_store=ConfigStore(Settings, tmp_path / "settings.json"),
            sender_states={},
            event_bus=EventBus(),
            pending_capabilities={},
        ),
        prefix="/api/v1/voice",
    )
    return TestClient(app).get("/api/v1/voice/status").json()


def test_real_detector_with_real_providers_is_production_ready(tmp_path: Path) -> None:
    assert _status_for_detector(tmp_path, "OnnxWakeWordDetector")["is_production_ready"] is True


def test_placeholder_detector_marks_pipeline_as_not_ready(tmp_path: Path) -> None:
    """Regresja: `is_production_ready` sprawdzało wcześniej tylko atrapy STT/TTS,
    więc pipeline z niezaładowanym modelem `.onnx` (cicha degradacja do detektora
    reagującego na głośność, nie na słowo) raportował się jako gotowy."""
    assert _status_for_detector(tmp_path, "ThresholdEnergyWakeWordDetector")["is_production_ready"] is False
