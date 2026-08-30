"""Warstwa ścieżek i konfiguracji środowiskowej (`shared/paths.py`, `shared/env.py`).

Testowana, bo to **jedyna rzecz stojąca między konteneryzacją a katalogiem `data/`
wylądowanym w `site-packages`**: `get_service_root()` szuka `pyproject.toml` w górę od
pliku źródłowego, więc w obrazie Dockera i w bundlu PyInstallera wskazuje miejsce
przypadkowe. Regresja tutaj objawia się dopiero na maszynie docelowej, po `docker pull`,
jako zniknięte sesje i klucze — czyli w najgorszym możliwym momencie.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from server.config import Settings, load_settings
from server.main import _resolve_wakeword_model_path
from shared import config_dir, data_dir, env_bool, env_int, env_str, load_dotenv
from shared.env import ENV_FILE_VARIABLE
from shared.paths import CONFIG_DIR_VARIABLE, DATA_DIR_VARIABLE

# ------------------------------------------------------------------------------
# Katalogi
# ------------------------------------------------------------------------------


def test_data_dir_falls_back_to_service_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DATA_DIR_VARIABLE, raising=False)

    resolved = data_dir(__file__)

    assert resolved.name == "data"
    assert resolved.parent.name == "server"


def test_data_dir_env_override_wins_and_creates_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "wolumen" / "dane"
    monkeypatch.setenv(DATA_DIR_VARIABLE, str(target))

    resolved = data_dir(__file__)

    assert resolved == target.resolve()
    assert resolved.is_dir()


def test_config_dir_accepts_own_env_variable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Satelita i serwer potrafią działać na jednej maszynie — satelita musi mieć
    własną zmienną, żeby `REGIS_CONFIG_DIR` serwera ich nie zlepił."""
    monkeypatch.setenv(CONFIG_DIR_VARIABLE, str(tmp_path / "serwer"))
    monkeypatch.setenv("REGIS_SATELLITE_CONFIG_DIR", str(tmp_path / "satelita"))

    assert config_dir(__file__) == (tmp_path / "serwer").resolve()
    assert config_dir(__file__, env_var="REGIS_SATELLITE_CONFIG_DIR") == (tmp_path / "satelita").resolve()


# ------------------------------------------------------------------------------
# Ścieżka modelu wake-word — zgodność wsteczna z prefiksem `data/`
# ------------------------------------------------------------------------------


def test_wakeword_path_relative_to_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(DATA_DIR_VARIABLE, str(tmp_path))

    assert _resolve_wakeword_model_path("wakeword/regis.onnx") == tmp_path.resolve() / "wakeword" / "regis.onnx"


def test_wakeword_legacy_data_prefix_is_stripped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Istniejące konfiguracje trzymają `data/wakeword/regis.onnx` — ścieżkę względną
    wobec korzenia usługi. Bez obcięcia prefiksu wyszłoby `<data>/data/wakeword/...`,
    a brak pliku kończy się w `main.py` cichą degradacją do placeholdera amplitudy."""
    monkeypatch.setenv(DATA_DIR_VARIABLE, str(tmp_path))

    assert _resolve_wakeword_model_path("data/wakeword/regis.onnx") == tmp_path.resolve() / "wakeword" / "regis.onnx"


def test_wakeword_absolute_path_is_left_alone(tmp_path: Path) -> None:
    absolute = tmp_path / "gdziekolwiek" / "model.onnx"

    assert _resolve_wakeword_model_path(str(absolute)) == absolute


# ------------------------------------------------------------------------------
# .env
# ------------------------------------------------------------------------------


def test_dotenv_parses_and_does_not_override_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# komentarz",
                "",
                "REGIS_TEST_PLAIN=wartość",
                'REGIS_TEST_QUOTED="w cudzysłowie"',
                "export REGIS_TEST_EXPORTED=trzy",
                "REGIS_TEST_ALREADY_SET=z pliku",
                "linia bez znaku równości",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(ENV_FILE_VARIABLE, str(env_file))
    monkeypatch.setenv("REGIS_TEST_ALREADY_SET", "ze środowiska")
    for name in ("REGIS_TEST_PLAIN", "REGIS_TEST_QUOTED", "REGIS_TEST_EXPORTED"):
        monkeypatch.delenv(name, raising=False)

    loaded = load_dotenv(__file__)

    assert loaded == env_file
    assert os.environ["REGIS_TEST_PLAIN"] == "wartość"
    assert os.environ["REGIS_TEST_QUOTED"] == "w cudzysłowie"
    assert os.environ["REGIS_TEST_EXPORTED"] == "trzy"
    # `docker run -e` musi wygrywać z plikiem, inaczej wdrożenie jest nieprzewidywalne
    assert os.environ["REGIS_TEST_ALREADY_SET"] == "ze środowiska"


def test_typed_getters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REGIS_TEST_EMPTY", "   ")
    monkeypatch.setenv("REGIS_TEST_PORT", "9001")
    monkeypatch.setenv("REGIS_TEST_FLAG", "YES")
    monkeypatch.setenv("REGIS_TEST_BROKEN", "osiem")

    assert env_str("REGIS_TEST_EMPTY") is None
    assert env_str("REGIS_TEST_NIEUSTAWIONA") is None
    assert env_int("REGIS_TEST_PORT") == 9001
    assert env_bool("REGIS_TEST_FLAG") is True

    # Cicha degradacja do wartości domyślnej ukryłaby literówkę w docker-compose.yml
    with pytest.raises(ValueError):
        env_int("REGIS_TEST_BROKEN")
    with pytest.raises(ValueError):
        env_bool("REGIS_TEST_BROKEN")


# ------------------------------------------------------------------------------
# Overlay środowiskowy na `Settings`
# ------------------------------------------------------------------------------


def test_env_overlay_applies_only_to_deployment_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Overlay obejmuje wyłącznie `host`/`port`/`debug`. Zbiór MUSI pozostać rozłączny
    z tym, co zapisuje `PUT /api/v1/voice/client-config` — inaczej pierwszy zapis
    z Web UI zabetonowałby w pliku wartość pochodzącą ze środowiska."""
    monkeypatch.setenv(CONFIG_DIR_VARIABLE, str(tmp_path))
    from server.config import config_store

    monkeypatch.setattr(config_store, "config_path", tmp_path / "settings.json")
    config_store.save(Settings(host="127.0.0.1", port=8000, debug=False, wakeword_threshold=0.42))

    monkeypatch.setenv("REGIS_HOST", "0.0.0.0")
    monkeypatch.setenv("REGIS_PORT", "9999")
    monkeypatch.setenv("REGIS_DEBUG", "true")

    settings = load_settings()

    assert (settings.host, settings.port, settings.debug) == ("0.0.0.0", 9999, True)
    # Pole edytowalne z Web UI zostaje takie, jakie jest w pliku
    assert settings.wakeword_threshold == 0.42
    # ...a plik na dysku nie został dotknięty przez sam odczyt
    assert config_store.load().port == 8000
