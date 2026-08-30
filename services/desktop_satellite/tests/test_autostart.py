"""Autostart satelity — format wpisu i przełączanie stanu.

Testowalne jest to, co jest czystą decyzją (jakie polecenie wpisujemy, jaki `.desktop`
generujemy); sam zapis do rejestru Windows i do `~/.config/autostart` jest sprawdzany
przez podmianę katalogu domowego, żeby test nie dotykał prawdziwej konfiguracji
użytkownika, który go uruchamia.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from desktop_satellite import autostart


def test_launch_command_from_sources_runs_the_module() -> None:
    """Ze źródeł przełącznik ma działać bez budowania aplikacji — inaczej testowanie
    autostartu wymagałoby pełnego builda przy każdej zmianie."""
    command = autostart.launch_command()

    assert command[0] == sys.executable
    assert command[1:] == ["-m", "desktop_satellite.main"]


def test_launch_command_when_frozen_is_the_executable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autostart, "is_frozen", lambda: True)

    assert autostart.launch_command() == [sys.executable]


def test_desktop_entry_has_fields_required_by_xdg() -> None:
    """Brak `Type` albo `Exec` sprawia, że środowisko graficzne po cichu ignoruje plik —
    autostart „jest włączony" i nic się nie uruchamia."""
    content = autostart.desktop_entry_content()

    assert content.startswith("[Desktop Entry]\n")
    for required in ("Type=Application", "Name=", "Exec=", "Terminal=false"):
        assert required in content, required
    assert sys.executable in content


@pytest.mark.skipif(sys.platform != "linux", reason="ścieżka XDG dotyczy Linuksa")
def test_enable_disable_roundtrip_linux(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert autostart.is_enabled() is False
    assert autostart.enable() is True
    assert autostart.is_enabled() is True
    assert (tmp_path / "autostart" / autostart.LINUX_DESKTOP_FILE_NAME).is_file()

    assert autostart.disable() is True
    assert autostart.is_enabled() is False


@pytest.mark.skipif(sys.platform != "win32", reason="klucz Run dotyczy Windows")
def test_enable_disable_roundtrip_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zapis idzie do gałęzi UŻYTKOWNIKA (HKCU), więc test nie potrzebuje uprawnień
    administratora. Używa własnej nazwy wartości, żeby nie ruszyć wpisu, który
    uruchamiający ten test może mieć realnie ustawiony."""
    monkeypatch.setattr(autostart, "WINDOWS_VALUE_NAME", "RegisSatelliteTest")

    try:
        assert autostart.is_enabled() is False
        assert autostart.enable() is True
        assert autostart.is_enabled() is True
        assert sys.executable in (autostart._windows_read() or "")

        assert autostart.disable() is True
        assert autostart.is_enabled() is False
    finally:
        autostart.disable()


def test_toggle_reports_state_after_switching(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Menu zasobnika rysuje ptaszek na podstawie tego, co zwróci `toggle()`."""
    if sys.platform == "linux":
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    elif sys.platform == "win32":
        monkeypatch.setattr(autostart, "WINDOWS_VALUE_NAME", "RegisSatelliteTest")
    else:
        pytest.skip("autostart nieobsługiwany na tej platformie")

    try:
        assert autostart.toggle() is True
        assert autostart.toggle() is False
    finally:
        autostart.disable()
