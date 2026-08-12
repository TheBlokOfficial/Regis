# Instrukcje dla Agenta AI (Regis Monorepo)

## 1. Kontekst Projektu
Projekt **Regis** to system usług rozproszonych w architekturze Monorepo Python (`uv workspace`).
Serwer główny (`services/server`) pełni rolę **Systemu Operacyjnego Agenta AI (Agent OS)** komunikującego się z satelitami poprzez WebSockets.

## 2. Podstawowe Polecenia
- **Synchronizacja środowiska**: `python -m uv sync`
- **Uruchomienie serwera dev**: `python -m uv run uvicorn server.main:app --reload`
- **Uruchomienie skryptu głównego**: `python -m uv run python -m server.main`

## 3. Zasady Architektury i Kodowania
- **Struktura**:
  - `services/` – Niezależne usługi sieciowe i mikrousługi (np. `services/server`).
  - `packages/` – Wspólne biblioteki kodowe (np. `packages/shared`).
- **Warstwa `services/server`**:
  - `core/` – Rdzeń agenta (`AgentEngine`), pamięć, logika.
  - `network/` – Adaptery I/O dla satelitów (FastAPI, WebSockets).
- **Komunikacja i Logowanie**:
  - Wewnętrzne zdarzenia: `EventBus` z `packages/shared` + silnie typowane zdarzenia Pydantic wewnątrz usługi.
  - Logowanie: Używaj wyłącznie `from shared import get_logger`.
