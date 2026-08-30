"""Cykl życia `SatelliteApp` — pętla połączenia w wątku roboczym.

Testowane bez mikrofonu, głośnika i serwera: sprawdzamy to, co jest **nowe** względem
dawnej pętli w `main.py`, czyli sterowanie z zewnętrznego wątku i wystawianie stanu.
Bez tego zasobnik nie ma czego pokazać, a bez zasobnika tryb bezokienkowy nie ma
żadnego interfejsu (patrz `tray.py`).
"""

from __future__ import annotations

import time

import pytest
from desktop_satellite.app import AppStatus, LinkState, SatelliteApp


class _FakeMic:
    def start(self) -> None: ...

    def stop(self) -> None: ...


class _FakeSpeaker:
    pass


@pytest.fixture(autouse=True)
def _no_hardware(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pętla tworzy mikrofon i głośnik od razu — bez podmiany test wymagałby PortAudio.
    Skrócony backoff, żeby kolejne zmiany stanu następowały w czasie testu."""
    monkeypatch.setattr("desktop_satellite.app.MicCapture", _FakeMic)
    monkeypatch.setattr("desktop_satellite.app.SpeakerPlayback", _FakeSpeaker)
    monkeypatch.setattr("desktop_satellite.app.RECONNECT_DELAY_SECONDS", 0.05)


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def test_status_starts_as_searching_and_carries_sender_id() -> None:
    app = SatelliteApp(sender_id="sat_abc")

    assert app.status.state is LinkState.SEARCHING
    assert app.status.sender_id == "sat_abc"


def test_discovery_failure_is_reported_to_the_listener(monkeypatch: pytest.MonkeyPatch) -> None:
    """Brak serwera to normalny stan (satelita wstaje z systemem, zanim serwer zdąży),
    więc musi być widoczny w zasobniku, a nie tylko w logu."""

    async def never_finds(_timeout: float) -> None:
        return None

    monkeypatch.setattr("desktop_satellite.app.discover_server", never_finds)

    seen: list[AppStatus] = []
    app = SatelliteApp(sender_id="sat_abc", on_status_change=seen.append)
    app.start()
    try:
        assert _wait_until(lambda: any("Ponawiam" in s.label for s in seen))
        assert app.status.state is LinkState.SEARCHING
    finally:
        app.stop()


def test_stop_from_another_thread_ends_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """`stop()` woła się z wątku zasobnika, nie z pętli — o poprawność dba
    `call_soon_threadsafe`, bezpośrednie `task.cancel()` byłoby wyścigiem."""

    async def never_finds(_timeout: float) -> None:
        return None

    monkeypatch.setattr("desktop_satellite.app.discover_server", never_finds)

    app = SatelliteApp(sender_id="sat_abc")
    app.start()

    # Zatrzymanie NATYCHMIAST po starcie — przypadek graniczny, w którym pętli jeszcze
    # nie ma. Dawniej `stop()` trafiało wtedy w `self._loop is None` i po cichu nie
    # robiło nic: ikona znikała, a proces zostawał uruchomiony.
    app.stop(timeout=5.0)

    assert app.status.state is LinkState.STOPPED
    assert app._thread is None


def test_listener_exception_does_not_kill_the_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Awaria warstwy prezentacji nie może zabić połączenia — ten sam wzorzec co
    obserwator prób w `ai/llm/router.py` po stronie serwera."""

    async def never_finds(_timeout: float) -> None:
        return None

    monkeypatch.setattr("desktop_satellite.app.discover_server", never_finds)

    calls: list[int] = []

    def exploding(_status: AppStatus) -> None:
        calls.append(1)
        raise RuntimeError("zasobnik padł")

    app = SatelliteApp(sender_id="sat_abc", on_status_change=exploding)
    app.start()
    try:
        # Kilka zmian stanu z rzędu = pętla przeżyła pierwszy wyjątek obserwatora
        assert _wait_until(lambda: len(calls) >= 3)
    finally:
        app.stop()


def test_status_label_is_human_readable() -> None:
    connected = AppStatus(state=LinkState.CONNECTED, sender_id="s", server_url="ws://1.2.3.4:8000/ws/voice")
    searching = AppStatus(state=LinkState.SEARCHING, sender_id="s", detail="Serwer nie znaleziony. Ponawiam...")
    stopped = AppStatus(state=LinkState.STOPPED, sender_id="s")

    assert "ws://1.2.3.4:8000" in connected.label
    assert searching.label == "Serwer nie znaleziony. Ponawiam..."
    assert stopped.label == "Zatrzymana"
