"""Gdzie usługa trzyma swoje dane i konfigurację — jedno pojęcie zamiast wywołań
`get_service_root(__file__) / "data"` rozsianych po tuzinie modułów.

**Dlaczego to nie może zostać przy `get_service_root()`.** Ta funkcja
(`shared/config.py`) szuka `pyproject.toml` w górę od pliku **źródłowego**. Wzorzec
działa bez zarzutu przy uruchomieniu z checkoutu i przewraca się w obu docelowych
postaciach produkcyjnych:

* **kontener** — pakiet `server` siedzi w `site-packages`, gdzie żadnego `pyproject.toml`
  nie ma; funkcja spada wtedy na katalog samego modułu, więc `data/` lądowałoby wewnątrz
  `site-packages` i znikało przy każdej aktualizacji obrazu;
* **satelita zamrożona PyInstallerem** — źródła są rozpakowane do katalogu tymczasowego,
  więc `config/settings.json` powstawałby od nowa przy każdym starcie, a wraz z nim nowy
  `sender_id`. Satelita traciłaby tożsamość i wypadała z rejestru klientów w Web UI.

Stąd kolejność: **zmienna środowiskowa, a dopiero potem korzeń usługi**. W kontenerze
`REGIS_DATA_DIR=/data` wskazuje wolumen; lokalnie nie ustawia się niczego i wszystko
zostaje tam, gdzie było.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from shared.config import get_service_root
from shared.env import env_str

DATA_DIR_VARIABLE = "REGIS_DATA_DIR"
CONFIG_DIR_VARIABLE = "REGIS_CONFIG_DIR"


def data_dir(start_path: Path | str, env_var: str = DATA_DIR_VARIABLE) -> Path:
    """Katalog danych usługi: `$REGIS_DATA_DIR`, w przeciwnym razie `<korzeń usługi>/data`.

    Katalog jest tworzony, jeśli nie istnieje — magazyny i tak robiły to same, każdy
    osobno, tuż po wyliczeniu ścieżki.

    :param env_var: Nazwa zmiennej nadpisującej. Podmieniana przez usługi, które muszą
        dać się skonfigurować niezależnie od serwera, choć działają na tej samej maszynie
        (satelita desktopowa — patrz `desktop_satellite/config.py`).
    """
    return _resolve(env_str(env_var), get_service_root(start_path) / "data")


def config_dir(start_path: Path | str, env_var: str = CONFIG_DIR_VARIABLE) -> Path:
    """Katalog konfiguracji usługi: `$REGIS_CONFIG_DIR`, w przeciwnym razie `<korzeń usługi>/config`.

    :param env_var: jak w `data_dir()`.
    """
    return _resolve(env_str(env_var), get_service_root(start_path) / "config")


def user_state_dir(app_name: str) -> Path:
    """Katalog na dane aplikacji **desktopowej**, per użytkownik systemu.

    `%APPDATA%\\<app_name>` na Windows, `$XDG_CONFIG_HOME/<app_name>` (albo
    `~/.config/<app_name>`) na Linux. Używane przez satelitę w postaci zainstalowanej,
    gdzie katalog programu bywa tylko do odczytu, a katalog źródeł nie istnieje wcale.
    """
    folder = app_name if sys.platform == "win32" else app_name.lower()
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return _resolve(None, base / folder)


def is_frozen() -> bool:
    """Czy proces działa jako aplikacja zamrożona (PyInstaller), a nie z checkoutu.

    Rozstrzyga, czy ścieżki wolno wyprowadzać z położenia plików źródłowych —
    w bundlu wskazują katalog tymczasowy, kasowany między uruchomieniami.
    """
    return bool(getattr(sys, "frozen", False))


def _resolve(override: str | None, fallback: Path) -> Path:
    path = (Path(override).expanduser() if override else fallback).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
