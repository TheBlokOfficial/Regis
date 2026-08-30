# Changelog

Wszystkie istotne zmiany w Systemie Regis. Format wg [Keep a Changelog](https://keepachangelog.com/pl/1.1.0/),
wersjonowanie wg [SemVer](https://semver.org/lang/pl/).

Wersja produktu żyje w `packages/shared/src/shared/version.py` — to jedyne źródło prawdy.
Runbook wydania: `docs/onboarding.md`, sekcja „Wydanie".

## [0.2.0] — w przygotowaniu

Pierwsze wydanie przeznaczone do realnego wdrożenia: serwer w kontenerze, satelita jako
zainstalowana aplikacja, konfiguracja przez środowisko.

### Dodane
- **Wygaszanie sesji po bezczynności** — historia rozmowy z satelitą jest czyszczona po
  `satellite_session_idle_ttl_seconds` (domyślnie 5 min). Satelita używa jednego `session_id`
  przez cały czas istnienia, więc bez tego model dostawał wiadomości sprzed wielu godzin jako
  bieżącą rozmowę. Czat Web UI nie wygasa — politykę wnosi brzeg kompozycji, nie kernel.
- **Sufit utrwalanych wiadomości** (`max_persisted_messages`, domyślnie 200) — chroni plik sesji
  przed nieskończonym narastaniem także tam, gdzie historia ma żyć długo.
- **Warstwa ścieżek** (`shared/paths.py`) — `REGIS_DATA_DIR` / `REGIS_CONFIG_DIR` decydują,
  gdzie usługa trzyma dane i konfigurację. Bez tego `data/` w kontenerze lądowałoby
  w `site-packages` i znikało przy aktualizacji obrazu, a satelita zamrożona PyInstallerem
  generowałaby nowy `sender_id` przy każdym starcie.
- **Konfiguracja ze środowiska** (`shared/env.py`) — wczytywanie `.env` (własny parser, bez
  nowej zależności) i nadpisania `REGIS_HOST` / `REGIS_PORT` / `REGIS_DEBUG`. Zmienne obecne
  w środowisku wygrywają z plikiem, więc `docker compose` jest przewidywalny. Wzorzec
  `.env.example` w korzeniu repozytorium.
- **Referencje sekretów `env:NAZWA`** (`shared/secrets.py`) — wartość klucza API dostawcy albo
  tokenu Home Assistant może wskazywać zmienną środowiskową zamiast trzymać sekret w pliku.
  Wstecznie zgodne: istniejące klucze wpisane wprost działają dalej, nie ma czego migrować.
  Model wielu nazwanych instancji zostaje nietknięty — każdy preset może wskazywać inną zmienną.
  Web UI pokazuje referencję wprost (to nazwa zmiennej, nie sekret) i podpowiada składnię.
- **Obraz Dockera i runbook wdrożenia** (`services/server/Dockerfile`, `docker-compose.yml`,
  `deploy/`) — cel: Raspberry Pi 5 / Pi OS Lite 64-bit, obraz budowany natywnie na Pi, bez QEMU
  i bez rejestru. `network_mode: host` jest warunkiem koniecznym auto-discovery satelit
  (UDP broadcast nie wychodzi z sieci bridge). `deploy/deploy.sh` aktualizuje wersję i czeka
  na `/api/v1/health` zamiast kończyć się na `up -d`.
- **Typowany kontrakt ramek WS** (`shared/voice_frames.py`) — jedyny kontrakt między usługami
  nietypowany Pydantikiem dostał modele i kodek. Format na drucie bez zmian (test złotego
  wzorca), więc stara satelita i nowy serwer pozostają zgodne.
- **Rejestr obecności klienta** (`voice/presence.py`) zamiast trzech gołych kolekcji wędrujących
  przez sygnatury dwóch fabryk routerów; `create_voice_router` schodzi z 9 do 7 parametrów,
  a rozłączenie sprząta cały ślad jednym wywołaniem.
- Jedno źródło prawdy dla wersji produktu (`shared/version.py`) + `CHANGELOG.md` i runbook wydania.
- `GET /api/v1/health` zwraca `app_name` i `version` — dashboard Web UI pokazuje wreszcie nazwę
  aplikacji zamiast zawsze wpadać w gałąź zapasową.

### Zmienione
- `GET /api/v1/voice/status` liczy `is_production_ready` z właściwości `is_placeholder`
  konkretów, a nie z prefiksu nazwy klasy (`name.startswith("Mock")`) — dawna wersja
  milcząco przestałaby działać przy pierwszym dev-providerze nazwanym inaczej.
- README nie twierdzi już, że „żaden parametr nie jest odczytywany ze zmiennych środowiskowych" —
  po wprowadzeniu warstwy środowiskowej to zdanie przestało być prawdziwe.
- Usunięte pole `version` z `Settings` i `config/settings.json` — wersja nie jest już rzeczą,
  którą użytkownik edytuje ręcznie w konfiguracji.
- `HealthResponse.shared_version` → `HealthResponse.version` (wersja produktu, nie samego pakietu
  `shared`). Zmiana kontraktu REST; żaden konsument w Web UI z tego pola nie korzystał.

## [0.1.0] — 2026-08-25

Faza dynamicznego prototypu, bez tagów w repozytorium. Stan na koniec fazy: kernel agenta z pętlą
ReAct, `WorldEngine` (Home Assistant, pokoje, nadawcy), pipeline głosowy satelit (wake-word/STT/TTS),
telemetria wywołań LLM w SQLite, wbudowana konsola Web UI, satelita desktopowa Windows/Linux.
Szczegóły: historia gita (113 commitów) oraz `docs/manifest.md`.
