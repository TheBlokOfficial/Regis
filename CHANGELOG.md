# Changelog

Wszystkie istotne zmiany w Systemie Regis. Format wg [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
wersjonowanie wg [SemVer](https://semver.org/lang/pl/).

Wersja produktu żyje w `packages/shared/src/shared/version.py` — to jedyne źródło prawdy.
Runbook wydania: `docs/onboarding.md`, sekcja „Wydanie".

## [0.2.0] — w przygotowaniu

Pierwsze wydanie przeznaczone do realnego wdrożenia: serwer w kontenerze, satelita jako
zainstalowana aplikacja, konfiguracja przez środowisko.

### Dodane
- Jedno źródło prawdy dla wersji produktu (`shared/version.py`) + `CHANGELOG.md` i runbook wydania.
- `GET /api/v1/health` zwraca `app_name` i `version` — dashboard Web UI pokazuje wreszcie nazwę
  aplikacji zamiast zawsze wpadać w gałąź zapasową.

### Zmienione
- Usunięte pole `version` z `Settings` i `config/settings.json` — wersja nie jest już rzeczą,
  którą użytkownik edytuje ręcznie w konfiguracji.
- `HealthResponse.shared_version` → `HealthResponse.version` (wersja produktu, nie samego pakietu
  `shared`). Zmiana kontraktu REST; żaden konsument w Web UI z tego pola nie korzystał.

## [0.1.0] — 2026-08-25

Faza dynamicznego prototypu, bez tagów w repozytorium. Stan na koniec fazy: kernel agenta z pętlą
ReAct, `WorldEngine` (Home Assistant, pokoje, nadawcy), pipeline głosowy satelit (wake-word/STT/TTS),
telemetria wywołań LLM w SQLite, wbudowana konsola Web UI, satelita desktopowa Windows/Linux.
Szczegóły: historia gita (113 commitów) oraz `docs/manifest.md`.
