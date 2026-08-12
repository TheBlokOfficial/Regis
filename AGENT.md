# Instrukcje dla Agenta AI (Regis Monorepo)

## 1. Pierwsze zapoznanie z projektem (Start sesji)
- Podczas pierwszego zapoznania się z projektem przeczytaj dokumenty w katalogu `docs/`:
  - `docs/manifest.md` – Wizja architektury i stos technologiczny.
  - `docs/onboarding.md` – Szybki start i weryfikacja środowiska.

## 2. Procedura zakończenia sesji (Koniec pracy)
- Gdy użytkownik zasygnalizuje koniec sesji (np. *"kończymy sesję"*, *"na dzisiaj starczy"*):
  1. Zwerfikuj zmodyfikowane pliki (`git status`).
  2. Wykonaj commit z czytelnym i zwięzłym opisem wprowadzonych zmian.
  3. Wykonaj `git push` do repozytorium GitHub (`origin master`).

## 3. Kontekst Projektu
Projekt **Regis** to system usług rozproszonych w architekturze Monorepo Python (`uv workspace`).
Serwer główny (`services/server`) pełni rolę **Systemu Operacyjnego Agenta AI (Agent OS)** komunikującego się z satelitami poprzez WebSockets.

## 4. Podstawowe Polecenia
- **Synchronizacja środowiska**: `python -m uv sync`
- **Uruchomienie serwera dev**: `python -m uv run uvicorn server.main:app --reload`
- **Uruchomienie skryptu głównego**: `python -m uv run python -m server.main`

## 5. Zasady Architektura i Kodowania
- **Struktura**:
  - `services/` – Niezależne usługi sieciowe i mikrousługi (np. `services/server`).
  - `packages/` – Wspólne biblioteki kodowe (np. `packages/shared`).
- **Warstwa `services/server`**:
  - `core/` – Rdzeń agenta (`AgentEngine`), pamięć, logika.
  - `network/` – Adaptery I/O dla satelitów (FastAPI, WebSockets).
- **Komunikacja i Logowanie**:
  - Wewnętrzne zdarzenia: `EventBus` z `packages/shared` + silnie typowane zdarzenia Pydantic wewnątrz usługi.
  - Logowanie: Używaj wyłącznie `from shared import get_logger`.
