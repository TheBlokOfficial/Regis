# syntax=docker/dockerfile:1
#
# Obraz serwera Regis. Kontekst budowania to KORZEŃ REPOZYTORIUM (potrzebne są
# `uv.lock` i `packages/shared`), więc buduj przez `docker compose build`, nie przez
# `docker build services/server`.
#
# Cel: Raspberry Pi 5 / Raspberry Pi OS Lite 64-bit, obraz budowany NATYWNIE na Pi
# (`docker compose build`) — bez QEMU i bez rejestru obrazów. Przeniesienie na
# mini-PC amd64 nie wymaga żadnej zmiany w tym pliku, tylko rebuildu na tamtej maszynie.
#
# Python 3.13 jest bezpieczny na arm64: `onnxruntime` 1.29 (zależność `livekit-wakeword`,
# czyli wake-word) publikuje koło `cp313-manylinux_2_28_aarch64`, a bookworm ma glibc 2.36.

# ------------------------------------------------------------------------------
# Etap 1 — budowa środowiska
# ------------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Najpierw SAME manifesty i lock. Ta warstwa zmienia się wyłącznie przy zmianie
# zależności, więc rebuild po zmianie kodu nie powtarza instalacji — na Pi to różnica
# między kilkunastoma sekundami a kilkoma minutami.
# `--no-install-workspace` instaluje wyłącznie zależności zewnętrzne, bez `shared`
# i `server` (których źródeł jeszcze tu nie ma).
# README.md w komplecie: korzeniowy `pyproject.toml` deklaruje `readme`, a hatchling
# wymaga tego pliku przy budowie kół `shared`/`server` w kroku drugim.
COPY pyproject.toml uv.lock README.md ./
COPY packages/shared/pyproject.toml packages/shared/
COPY services/server/pyproject.toml services/server/
COPY services/desktop_satellite/pyproject.toml services/desktop_satellite/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package server --no-install-workspace

# Dopiero teraz kod. `--package server` pomija `desktop_satellite`, więc do obrazu
# nie trafia `sounddevice` ani PortAudio — serwer nie dotyka sprzętu audio.
COPY packages/ packages/
COPY services/ services/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package server

# ------------------------------------------------------------------------------
# Etap 2 — obraz uruchomieniowy
# ------------------------------------------------------------------------------
FROM python:3.13-slim-bookworm AS runtime

# uid 1000 pokrywa się z pierwszym użytkownikiem Raspberry Pi OS, więc bind-mounty
# `./data` i `./config` z hosta są zapisywalne bez `chown` i bez roota w kontenerze.
RUN useradd --create-home --uid 1000 regis

WORKDIR /app
COPY --from=build --chown=regis:regis /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    REGIS_DATA_DIR=/data \
    REGIS_CONFIG_DIR=/config

# Katalogi istnieją także bez podmontowanego wolumenu — kontener wystartuje wtedy
# na danych efemerycznych zamiast wywalać się przy pierwszym zapisie.
RUN mkdir -p /data /config && chown regis:regis /data /config
VOLUME ["/data", "/config"]

USER regis
EXPOSE 8000

# `network_mode: host` w compose sprawia, że `localhost` to host — a to i tak ta sama
# maszyna. Port czytany ze środowiska, żeby healthcheck nie rozjechał się z REGIS_PORT.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,urllib.request;urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('REGIS_PORT','8000')}/api/v1/health\",timeout=4)"

CMD ["python", "-m", "server.main"]
