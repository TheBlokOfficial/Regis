"""Uruchamianie satelity razem z systemem — Windows i Linux.

Autostart jest **przełącznikiem w menu zasobnika**, nigdy skutkiem ubocznym instalacji:
program, który sam wpisuje się do autostartu, jest zachowaniem, którego użytkownik ma
prawo się nie spodziewać. Skrypty instalacyjne co najwyżej proponują włączenie.

Dwie implementacje, bo to dwa różne mechanizmy systemowe, nie jeden z wariantami:

* **Windows** — klucz `HKCU\\...\\CurrentVersion\\Run`. `winreg` jest w bibliotece
  standardowej, więc nie dokłada zależności; zapis idzie do gałęzi UŻYTKOWNIKA, nie
  maszyny, więc nie wymaga uprawnień administratora.
* **Linux** — plik `.desktop` w `~/.config/autostart/` (XDG). Jednostka systemd byłaby
  kuszącym wyborem, ale startuje **przed** sesją graficzną użytkownika, a satelita
  potrzebuje działającego PulseAudio/PipeWire — czyli dokładnie tego, co przychodzi
  razem z sesją.

Ścieżka do uruchomienia jest wyliczana z `sys.executable`/`sys.argv`, więc działa
zarówno dla wersji zbudowanej (`sys.frozen`), jak i dla uruchomienia ze źródeł.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from shared import get_logger, is_frozen, user_state_dir

logger = get_logger("regis.desktop_satellite.autostart")

APP_NAME = "Regis Satellite"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_VALUE_NAME = "RegisSatellite"
LINUX_DESKTOP_FILE_NAME = "regis-satellite.desktop"


def launch_command() -> list[str]:
    """Polecenie, które ma wstawać razem z systemem.

    W wersji zbudowanej to sam plik wykonywalny; ze źródeł — interpreter z modułem,
    żeby przełącznik działał także podczas pracy nad kodem (inaczej testowanie
    autostartu wymagałoby budowania aplikacji przy każdej zmianie).
    """
    if is_frozen():
        return [sys.executable]
    return [sys.executable, "-m", "desktop_satellite.main"]


def is_supported() -> bool:
    """Czy na tym systemie w ogóle mamy jak włączyć autostart."""
    return sys.platform in ("win32", "linux")


def is_enabled() -> bool:
    if sys.platform == "win32":
        return _windows_read() is not None
    if sys.platform == "linux":
        return _linux_desktop_path().is_file()
    return False


def enable() -> bool:
    """:return: True, jeśli autostart jest po tej operacji włączony."""
    try:
        if sys.platform == "win32":
            _windows_write(_quote(launch_command()))
        elif sys.platform == "linux":
            _linux_write()
        else:
            logger.warning(f"Autostart nieobsługiwany na platformie [{sys.platform}].")
            return False
    except OSError as err:
        logger.error(f"Nie udało się włączyć autostartu: {err}")
        return False
    logger.info("Autostart włączony.")
    return True


def disable() -> bool:
    """:return: True, jeśli autostart jest po tej operacji wyłączony."""
    try:
        if sys.platform == "win32":
            _windows_delete()
        elif sys.platform == "linux":
            _linux_desktop_path().unlink(missing_ok=True)
        else:
            return True
    except OSError as err:
        logger.error(f"Nie udało się wyłączyć autostartu: {err}")
        return False
    logger.info("Autostart wyłączony.")
    return True


def toggle() -> bool:
    """Przełącza stan. :return: stan PO przełączeniu."""
    if is_enabled():
        disable()
    else:
        enable()
    return is_enabled()


# ------------------------------------------------------------------------------
# Windows — HKCU\...\Run
# ------------------------------------------------------------------------------


def _windows_read() -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, WINDOWS_VALUE_NAME)
            return str(value)
    except FileNotFoundError:
        return None


def _windows_write(command: str) -> None:
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, WINDOWS_VALUE_NAME, 0, winreg.REG_SZ, command)


def _windows_delete() -> None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, WINDOWS_VALUE_NAME)
    except FileNotFoundError:
        pass


# ------------------------------------------------------------------------------
# Linux — XDG autostart
# ------------------------------------------------------------------------------


def _linux_autostart_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart"


def _linux_desktop_path() -> Path:
    return _linux_autostart_dir() / LINUX_DESKTOP_FILE_NAME


def desktop_entry_content() -> str:
    """Zawartość pliku `.desktop`. Wydzielone, bo to format, który da się sprawdzić
    testem, w odróżnieniu od samego zapisu na dysk."""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        "Comment=Satelita głosowa Regis\n"
        f"Exec={_quote(launch_command())}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _linux_write() -> None:
    path = _linux_desktop_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(desktop_entry_content(), encoding="utf-8")


def _quote(command: list[str]) -> str:
    """Polecenie jako pojedynczy string, z cudzysłowami tam, gdzie trzeba.

    Na Windows `shlex.join` używa reguł POSIX (ucieczki przez ukośnik), które w rejestrze
    dają ścieżkę nie do uruchomienia — stąd osobna gałąź."""
    if sys.platform == "win32":
        return " ".join(f'"{part}"' if " " in part else part for part in command)
    return shlex.join(command)


# ------------------------------------------------------------------------------
# Pomocnicze dla menu zasobnika
# ------------------------------------------------------------------------------


def open_directory(path: Path) -> None:
    """Otwiera katalog w menedżerze plików systemu — używane przez pozycję menu
    „Otwórz katalog logów", jedyny wygodny wgląd w działanie aplikacji bez konsoli."""
    try:
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606 — obecne wyłącznie na Windows
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as err:
        logger.error(f"Nie udało się otworzyć katalogu [{path}]: {err}")


def logs_dir() -> Path:
    """Katalog logów satelity — ten sam, do którego pisze `main.py`."""
    return user_state_dir("Regis") / "logs"
