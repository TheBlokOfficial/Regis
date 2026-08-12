# Regis - System Usług Rozproszonych (Monorepo)

Projekt oparty o monorepo Python z wykorzystaniem menedżera pakietów [`uv`](https://github.com/astral-sh/uv) oraz architektury `uv workspace`.

## Struktura projektu

- `services/` - Usługi rozproszone (aplikacje sieciowe/mikrousługi):
  - `services/server/` - Główny serwer obsługujący WebSockets oraz API REST (FastAPI).
- `packages/` - Wspólne biblioteki kodowe (paczki pomocnicze/DTO/protokoły):
  - `packages/shared/` - Wspólna paczka kodu dla usług.
- `docs/` - Dokumentacja architektoniczna i onboardingowa (`manifest.md`, `onboarding.md`).


## Wymagania

- Python >= 3.11
- `uv` (`pip install uv`)

## Uruchamianie

### Instalacja / synchronizacja zależności
```bash
python -m uv sync
```

### Uruchomienie serwera
```bash
python -m uv run --package server uvicorn server.main:app --reload
```
