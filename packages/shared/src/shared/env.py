"""Konfiguracja ze środowiska: wczytanie pliku `.env` i typowany odczyt zmiennych.

Powstało pod dwie potrzeby wdrożeniowe, których pliki JSON nie obsłużą:

* **kontener** dostaje konfigurację przez `env_file`/`environment` w `docker-compose.yml`,
  a nie przez ręczną edycję `config/settings.json` w wolumenie;
* **klucze API** mogą żyć poza katalogiem danych, jako referencje `env:NAZWA`
  (patrz `shared/secrets.py`).

Świadomie bez zależności `python-dotenv`: parser poniżej ma kilkanaście linii, a projekt
konsekwentnie pisze takie rzeczy sam, gdy alternatywą jest zależność wielokrotnie większa
od potrzeby (precedens: `shared/discovery.py`, `desktop_satellite/vad.py`).

**Zmienne już obecne w środowisku wygrywają z plikiem `.env`** — inaczej `docker run -e`
i `env_file` byłyby nieprzewidywalne względem `.env` wpadającego do obrazu.
"""

from __future__ import annotations

import os
from pathlib import Path

from shared.logging import get_logger

logger = get_logger("regis.shared.env")

ENV_FILE_VARIABLE = "REGIS_ENV_FILE"
"""Jawne wskazanie pliku `.env`. Ma pierwszeństwo przed szukaniem w górę drzewa."""

_SEARCH_DEPTH = 6
"""Ile poziomów w górę od punktu startowego szukamy `.env` — z `services/<usługa>/src/...`
do korzenia repozytorium jest ich mniej."""


def find_env_file(start_path: Path | str) -> Path | None:
    """Odnajduje plik `.env`: najpierw `$REGIS_ENV_FILE`, potem w górę drzewa od `start_path`.

    :return: Ścieżka do istniejącego pliku albo `None` (brak `.env` to normalny stan —
        w kontenerze zmienne przychodzą wprost ze środowiska).
    """
    explicit = os.environ.get(ENV_FILE_VARIABLE, "").strip()
    if explicit:
        candidate = Path(explicit).expanduser()
        if candidate.is_file():
            return candidate
        logger.warning(f"{ENV_FILE_VARIABLE} wskazuje na nieistniejący plik [{candidate}] — pomijam.")
        return None

    current = Path(start_path).resolve()
    if current.is_file():
        current = current.parent
    for parent in [current, *current.parents][:_SEARCH_DEPTH]:
        candidate = parent / ".env"
        if candidate.is_file():
            return candidate
    return None


def load_dotenv(start_path: Path | str) -> Path | None:
    """Wczytuje `.env` do `os.environ`, **nie nadpisując** zmiennych już ustawionych.

    Format: `KLUCZ=wartość` po jednej na linię, puste linie i `#` ignorowane, opcjonalny
    prefiks `export `, opcjonalne cudzysłowy wokół wartości. Bez interpolacji `${...}`
    i bez wartości wielolinijkowych — gdyby kiedyś były potrzebne, to jest moment na
    sięgnięcie po prawdziwą bibliotekę, a nie na rozbudowę tego parsera.

    :return: Wczytany plik albo `None`, jeśli żadnego nie znaleziono.
    """
    env_file = find_env_file(start_path)
    if env_file is None:
        return None

    loaded = 0
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, separator, value = line.partition("=")
        if not separator:
            logger.warning(f"Pominięto linię bez '=' w [{env_file}]: {raw_line!r}")
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key in os.environ:
            continue
        os.environ[key] = value
        loaded += 1

    logger.info(f"Wczytano konfigurację ze środowiska [{env_file}]: {loaded} zmiennych.")
    return env_file


# ------------------------------------------------------------------------------
# Typowany odczyt — pusta zmienna znaczy "nie ustawiono", tak jak jej brak
# ------------------------------------------------------------------------------


def env_str(name: str) -> str | None:
    """Wartość zmiennej albo `None`, gdy nieustawiona lub pusta."""
    value = os.environ.get(name, "").strip()
    return value or None


def env_int(name: str) -> int | None:
    """:raises ValueError: gdy zmienna jest ustawiona, ale nie jest liczbą całkowitą —
    cicha degradacja do wartości domyślnej ukryłaby literówkę w `docker-compose.yml`."""
    raw = env_str(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as err:
        raise ValueError(f"Zmienna środowiskowa {name}='{raw}' nie jest liczbą całkowitą.") from err


def env_bool(name: str) -> bool | None:
    """`1/true/yes/on` (dowolna wielkość liter) = prawda; `0/false/no/off` = fałsz.

    :raises ValueError: przy wartości spoza obu list."""
    raw = env_str(name)
    if raw is None:
        return None
    lowered = raw.lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"Zmienna środowiskowa {name}='{raw}' nie jest wartością logiczną.")
