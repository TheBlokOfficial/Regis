"""Trwała, lokalna tożsamość satelity — `sender_id` generowany raz (UUID4) przy
pierwszym uruchomieniu i zapisywany na dysku, żeby kolejne starty nie wymagały
ręcznego podawania flagi.

**Gdzie leży ten plik, jest kwestią krytyczną, nie kosmetyczną.** Dotąd ścieżkę
wyprowadzał `get_service_root(__file__)`, czyli szukanie `pyproject.toml` w górę od
pliku źródłowego. Działa to wyłącznie przy uruchomieniu z checkoutu; w aplikacji
zamrożonej PyInstallerem źródła są rozpakowywane do katalogu **tymczasowego**, więc
plik konfiguracji powstawałby od nowa przy każdym starcie — a wraz z nim **nowy
`sender_id`**. Satelita gubiłaby wtedy tożsamość po każdym uruchomieniu i wypadała
z rejestru klientów w Web UI (przypisanie do pokoju, zatwierdzenie).

Stąd trzy poziomy, w tej kolejności:

1. `$REGIS_SATELLITE_CONFIG_DIR` — jawne wskazanie (testy, nietypowe instalacje).
   Zmienna jest **własna**, nie współdzielona z serwerem: obie usługi potrafią
   działać na jednej maszynie i `REGIS_CONFIG_DIR` serwera nie może ich zlepić.
2. postać zainstalowana (`sys.frozen`) — `%APPDATA%\\Regis` / `~/.config/regis`,
   czyli miejsce, które przeżywa aktualizację aplikacji i nie wymaga prawa zapisu
   do katalogu programu;
3. uruchomienie z checkoutu — `services/desktop_satellite/config/`, jak dotąd.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import BaseModel, Field
from shared import ConfigStore, config_dir, env_str, get_logger, is_frozen, user_state_dir

logger = get_logger("regis.desktop_satellite.config")

CONFIG_DIR_VARIABLE = "REGIS_SATELLITE_CONFIG_DIR"
APP_NAME = "Regis"


class SatelliteSettings(BaseModel):
    """Lokalna konfiguracja satelity."""

    sender_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Trwały opaque sender_id")


def resolve_config_dir() -> Path:
    """Katalog konfiguracji satelity — patrz trzy poziomy w docstringu modułu."""
    override = env_str(CONFIG_DIR_VARIABLE)
    if override or not is_frozen():
        return config_dir(__file__, env_var=CONFIG_DIR_VARIABLE)
    return user_state_dir(APP_NAME)


CONFIG_PATH = resolve_config_dir() / "settings.json"

config_store = ConfigStore(SatelliteSettings, CONFIG_PATH)


def load_or_create_sender_id() -> str:
    """Wczytuje `sender_id`, tworząc plik z nowym UUID4 przy pierwszym uruchomieniu.

    Przejście z uruchamiania ze źródeł na wersję zainstalowaną zmienia lokalizację
    pliku, więc **nowa instalacja dostaje nowy `sender_id`** i wymaga ponownego
    zatwierdzenia w Web UI. Żeby zachować dotychczasową tożsamość, wystarczy
    skopiować stary `config/settings.json` do nowej lokalizacji — robią to skrypty
    instalacyjne (`install.ps1` / `install.sh`), a ścieżkę pokazuje menu w zasobniku.
    """
    settings = config_store.load()
    logger.debug(f"Konfiguracja satelity: [{CONFIG_PATH}]")
    return settings.sender_id
