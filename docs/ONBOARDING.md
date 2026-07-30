# Regis: Mapa Kodu (Onboarding)

Ten dokument to przewodnik po strukturze repozytorium. Wyjaśnia, co robi każdy katalog i każdy plik — prostym językiem, bez nadmiernego zagłębiania się w szczegóły implementacji. Jest przeznaczony zarówno dla człowieka wracającego do projektu po przerwie, jak i dla agenta AI rozpoczynającego pracę w projekcie.

Zanim zaczniesz czytać ten dokument, upewnij się, że zapoznałeś się z `docs/MANIFEST.md` — to on definiuje *dlaczego* kod jest zbudowany w taki, a nie inny sposób.

---

## Struktura Katalogów — Obraz Ogólny

```
regis/
│
├── src/                ← Cały kod źródłowy projektu (src layout)
│   ├── core/           ← Biblioteka wspólna — importowana przez wszystkich
│   ├── integrations/   ← Klienci zewnętrznych API (HA, MQTT, inne)
│   ├── controller/     ← Usługa RPi5: routing, rejestr encji, proxy
│   ├── controller/worker/  ← Usługa RPi5: headless worker LLM (fallback 1.5B) [przejściowy]
│   └── node/           ← Aplikacja Windows: UI + Worker + Satellite
│
├── config/             ← Konfiguracja statyczna (aliases, rooms, virtual_groups)
├── data/               ← Stan dynamiczny, logi, prompty (wykluczone z Git)
├── docs/               ← Dokumentacja projektu
├── tests/              ← Testy jednostkowe pytest
├── pyproject.toml      ← Definicja pakietu i zależności
├── pytest.ini          ← Konfiguracja testów
└── regis.bat           ← Uruchomienie aplikacji node (dev)
```

**Prosta zasada podziału:**
- `core/` = **mózg** — nie uruchamia się sam, ale wszystko go używa.
- `controller/` + `node/` = **dwa środowiska uruchomieniowe** — każde na innym sprzęcie.
- `integrations/` = **zmysły** — klienci zewnętrznych platform. Każda integracja to osobny plik.
- `data/` = **pamięć dynamiczna** — konfiguracja i stan, który przeżywa restarty.
- `config/` = **konfiguracja statyczna** — aliasy, pokoje, grupy wirtualne.

---

## `src/controller/` — Kontroler (RPi5)

**Rola:** Mózg systemu. Lekki daemon uruchamiany wyłącznie na Raspberry Pi 5 (jedna instancja globalna). Zarządza rejestrem węzłów i satelit, routingiem sesji oraz delegowaniem narzędzi do Home Assistant.

**Dystrybucja:** Pakiet `.whl` instalowany przez `pip` na Raspberry Pi 5 (Linux).

**Pliki:**
- `main.py` — entry point, uruchamia serwer uvicorn
- `app.py` — instancja FastAPI + lifespan (inicjalizacja klientów HA, rejestru)
- `registry.py` — logika rejestrów workerów i satelit, heartbeat, wybór najlepszego węzła
- `router.py` — proxy SSE: przekierowuje żądania czatu (tekst i audio) do aktywnych węzłów z failoverem
- `tools.py` — endpoint `/v1/tools/execute`: jedyne miejsce w systemie które komunikuje się z HA

> **Zasada Architektoniczna:** Kontroler jest jedynym źródłem prawdy dla Home Assistant.
> Węzły robocze nigdy nie komunikują się z HA bezpośrednio — zawsze przez `/v1/tools/execute`.

---

## `src/node/` — Węzeł (Windows PC)

**Rola:** Pełnoprawna **aplikacja Windows** z interfejsem terminalowym (stan obecny, konfiguracja przejściowa). Łączy trzy warstwy w jedną całość:
- **UI terminalowy** (dashboard, monitor konwersacji, monitor głosowy) — pierwszorzędny element
- **Worker LLM** (inferencja 9B) — uruchamiany jako ukryty proces w tle
- **Satellite audio** (VAD + WakeWord + przechwytywanie dźwięku) — uruchamiany jako ukryty proces w tle

Ikona w pasku zadań to jedynie mechanizm życia procesu — nie definicja aplikacji. W docelowej architekturze (patrz MANIFEST.md §3.6) Worker odpada z `node`, a Windows staje się czystą Satelitą z UI.

**Dystrybucja:** Windows Installer (`RegisNodeSetup.exe`) — budowany narzędziem Inno Setup. Wymaga Python zainstalowanego w systemie. Szczegóły: `docs/distribution_rfc.md`. **PyInstaller jest porzucony i nie jest używany.**

**Pliki:**
- `main.py` — entry point: jeśli brak `data/settings.json` → uruchamia wizard; jeśli istnieje → uruchamia serwis
- `wizard.py` — kreator konfiguracji (questionary) dla pierwszego uruchomienia
- `service.py` — **pełnoprawna usługa Windows** (biblioteka `pystray`); właściciel procesów Worker i Satellite. Wystawia mini HTTP API na `localhost:8099` dla dashboardu. Menu ma 3 pozycje: status, "Otwórz panel kontrolny", "Zamknij". Zamknięcie zawsze zatrzymuje wszystkie procesy.
- `dashboard.py` — panel kontrolny CLI; klient HTTP API serwisu. Wyświetla status usług, umożliwia start/stop Worker i Satellite, otwiera wizard i Monitor.
- `worker.py` — serwer HTTP węzła LLM (FastAPI); uruchamiany jako ukryty proces w tle
- `node.py` — klasa `WorkerNode`: inicjalizuje `LLMEngine`, obsługuje `handle_chat()`
- `satellite.py` — logika przechwytywania audio z mikrofonu i wysyłania do Kontrolera
- `monitor.py` — interaktywne narzędzie czatu tekstowego (Monitor konwersacji)
- `monitor_core.py` — wspólna logika wyświetlania eventów SSE
- `monitor_voice.py` — Monitor Głosowy (Live Dashboard): śledzenie pipeline'u audio w czasie rzeczywistym
- `stt_worker.py` — osobny proces STT (Whisper) uruchamiany przez Worker
- `ux.py` — style rich/questionary wspólne dla całego modułu node

**Flow pierwszego uruchomienia:**
1. `Uruchom.bat` → `regis-node.exe`
2. Brak `settings.json` → otwiera się konsola z wizardem questionary
3. Użytkownik konfiguruje: nazwa instancji, pokój, URL Kontrolera, tier modelu, które usługi uruchamiać
4. Zapisuje `data/settings.json` → konsola znika → usługa odpala się w tle (ikona pojawia się w pasku zadań)

**Architektura Service ←→ Dashboard:**
Serwis (`service.py`) jest właścicielem procesów (Worker, Satellite) i wystawia HTTP API na `localhost:8099`. Dashboard jest klientem — pyta serwis o status przez `GET /status` i wydaje komendy przez `POST /worker/toggle` itp. Dzięki temu serwis nie ma własnego UI zarządzania — deleguje je do dashboardu.

---

## `src/core/` — Serce Systemu

Pliki w tym katalogu **nigdy nie są uruchamiane bezpośrednio**. Są importowane przez usługi i przez siebie nawzajem.

### `llm_engine.py` — Silnik LLM
Zarządza całą komunikacją z Ollamą. Najbardziej centralny plik w projekcie.

Kluczowe odpowiedzialności:
- Buduje kompletny system prompt (tożsamość modelu z `data/prompts/` + opis narzędzi renderowany jako XML)
- Implementuje **pętlę ReAct** — wysyła zapytanie, parsuje odpowiedź, wykonuje narzędzia, powtarza
- Dla tieru `butler` (1.5B): używa **Structured Outputs** (JSON Schema przez Ollamę) zamiast ReAct
- Zarządza historią konwersacji (lista pełnych tur `user+assistant`, z limitem)
- **Droga A:** opisy narzędzi renderowane jako tekst XML (`<tools>`) do promptu, nie jako pole `tools` w API

### `stream_parser.py` — Parser Strumieniowy
Przetwarza surowy strumień tokenów z Ollamy i segreguje na trzy kanały:
- `<thought>...</thought>` → callback `on_thought_token` (wewnętrzny monolog modelu)
- `<action>...</action>` → przechwycone jako wywołanie narzędzia
- Reszta → callback `on_content_token` (to co widzi użytkownik)

Bufor Lookahead chroni przed tagami rozbitymi na dwa chunki TCP.

### `tools_registry.py` — Rejestr Narzędzi (lokalny)
Używany przez Kontroler. Weryfikuje uprawnienia tieru i wykonuje wywołania narzędzi przez klientów w `integrations/`. Zwraca wynik jako string JSON.

### `remote_tools_registry.py` — Rejestr Narzędzi (zdalny)
Używany przez Węzeł Roboczy. Zamiast wywoływać narzędzia lokalnie — deleguje je do Kontrolera przez HTTP POST `/v1/tools/execute`. Węzeł nigdy nie zna HA.

### `schemas.py` — Definicje Narzędzi
`BASE_TOOLS_SCHEMA` — lista wszystkich dostępnych narzędzi z opisami, parametrami i wymaganym tierem. To "menu narzędzi" systemu.

### `config.py` — Konfiguracja
Centralny punkt ładowania konfiguracji z `data/` i `config/`. Obsługuje profile (`ACTIVE_PROFILE` z `.env`). Plik zawiera również pozostawłość po epoce PyInstaller (`if getattr(sys, 'frozen', False)`) — dead code do usunięcia. Ładuje: `settings.<PROFILE>.json`, `config/aliases.json`, `config/virtual_groups.json`, `config/rooms.json`.

### `discovery.py` — Auto-Discovery
Implementacja Zero-Conf przez UDP Broadcast. Węzły i Satelity wykrywają Kontroler automatycznie w sieci lokalnej bez hardkodowania IP.

### `remote_client.py` — Klient Zdalny
Implementuje interfejs zgodny z `LLMEngine`, ale wysyła żądania do Kontrolera przez HTTP/SSE. Używany przez Satelitę.

### `stt_engine.py` — Silnik STT
Cienka warstwa na `faster-whisper`. Przyjmuje `BytesIO` z plikiem WAV, zwraca transkrypcję jako string.

### `logger.py` — System Logowania
Konfiguruje globalny system logowania dla danej usługi (`node` lub `controller`). Wywołaj `setup_logging("node")` raz przy starcie — ustawia dwa handlery: `FileHandler` (poziom DEBUG, zapis do `logs/<usługa>_YYYY-MM-DD.log`) oraz `StreamHandler` (poziom INFO, konsola). Wycisza szum z bibliotek zewnętrznych (urllib3, uvicorn.access). Katalog `logs/` jest wykluczony z Gita.

### `gemini_engine.py` — Silnik Gemini *(eksperymentalny)*
Alternatywny silnik LLM używający chmurowego API Google Gemini. Nie produkcyjny.

---

## `src/integrations/` — Klienci Zewnętrznych Usług

Katalog stanowi granicę między logiką systemu a światem zewnętrznym. Każda integracja to osobny plik.

### `ha_client.py` — Klient Home Assistant
Zarządza komunikacją z Home Assistant REST API. Używa `requests.Session()` — jedno długotrwałe połączenie. Obsługuje aliasy i wirtualne grupy urządzeń.

### `ha_mock.py` — Mock Home Assistant
Atrapa klienta HA do testowania bez fizycznego Home Assistanta.

---

## `data/` — Konfiguracja i Stan *(wykluczony z Git)*

### `settings.<PROFILE>.json`
Konfiguracja per instancja. Profil ładowany przez zmienną `ACTIVE_PROFILE` z `.env`. Dla Kontrolera na RPi: `settings.controller.json`. Dla paczki Portable: `settings.json` (tworzony przez wizard).

### `prompts/`
Pliki Markdown definiujące osobowość i instrukcje dla każdego tieru modelu:
- `tier_butler.md` — model 1.5B, NLU, minimalistyczny prompt Few-Shot JSON
- `tier_regis.md` — model 9B (qwen3.5:9b), pełny agent ReAct z Chain of Thought
 

### `rooms.json` *(w `config/`, nie w `data/`)*
Mapowanie pokójów na listy `entity_id` — wewnętrzna konfiguracja Regis niezależna od HA. Używana przez Spatial Context Filtering.

### `virtual_groups.json` *(w `config/`, nie w `data/`)*
Logiczne grupy urządzeń (np. "wszystkie żarówki w salonie"). Pozwala sterować wieloma urządzeniami jedną komendą.

### `aliases.json` *(w `config/`, nie w `data/`)*
Mapowanie przyjaznych nazw na `entity_id` HA.

---

## `docs/` — Dokumentacja Projektu

| Plik | Zawartość |
|---|---|
| `MANIFEST.md` | **Czytaj jako pierwszy.** Wizja, filozofia, rozstrzygnięte decyzje projektowe. |
| `AGENT_GUIDE.md` | Instrukcja dla agentów AI pracujących w projekcie. |
| `ONBOARDING.md` | Ten plik. Mapa kodu i struktury. |
| `arch_restrukturyzacja_2025.md` | Plan restrukturyzacji do dwóch usług (sesja 2026-07-23). |
| `distribution_rfc.md` | Decyzja o nowym systemie dystrybucji Windows (Inno Setup, porzucenie PyInstallera). |
| `auto_discovery_rfc.md` | Specyfikacja protokołu Zero-Conf UDP Broadcast. |
| `ux_monitor_tray_rfc.md` | Plan implementacji Monitora konwersacji i refaktoryzacji traya (3 etapy). |
| `architectural_debt_report.md` | Historyczny raport długu architektonicznego (już rozwiązany). |

---

## Jak Przepływa Jedno Polecenie (od A do Z)

```
Użytkownik mówi "włącz lampę" (przez mikrofon)
        ↓
[node/satellite.py]
Nagrywa audio WAV → wysyła POST /v1/chat/audio_stream do Kontrolera
        ↓
[controller/router.py]
Wybiera najlepszy aktywny węzeł z rejestru → proxy SSE do Worker
        ↓
[node/worker.py → node.py]
Odbiera audio → STT (Whisper) → transkrypcja "włącz lampę"
        ↓
[core/llm_engine.py] — pętla ReAct, iteracja 1
Buduje prompt (tier_regis.md + opisy narzędzi) → Ollama streamuje tokeny
        ↓
[core/stream_parser.py]
  <thought>Muszę sprawdzić urządzenia...</thought>  → on_thought_token
  <action>{"name": "get_devices"}</action>    → wywołanie narzędzia
        ↓
[core/remote_tools_registry.py]
POST /v1/tools/execute do Kontrolera (z room z kontekstu Satelity)
        ↓
[controller/tools.py → core/tools_registry.py]
Spatial Context Filtering: filtruje urządzenia do pokoju Satelity
→ ha_client.get_devices() → zwraca listę urządzeń pokoju
        ↓
[core/llm_engine.py] — pętla ReAct, iteracja 2
Wynik narzędzia w historii → Ollama: <action>{"name":"turn_on",...}</action>
        ↓
[integrations/ha_client.py]
POST do Home Assistant REST API → lampa się zapala
        ↓
[core/llm_engine.py] — pętla ReAct, iteracja 3
Model generuje finalną odpowiedź bez tool_call → koniec pętli
        ↓
SSE strumieniowane przez router do Satelity → Satelita odtwarza audio (TTS)
```

---

## Workflow Deweloperski

### Środowisko lokalne
1. Sklonuj repozytorium
2. `python -m venv .venv ; .venv\Scripts\Activate.ps1`
3. `pip install -e ".[all]"` — instaluje wszystkie zależności
4. Uruchom menedżer: `regis.bat`

### Deployment na Raspberry Pi
Z menedżera (`regis.bat`) wybierz "Wdróż serwer produkcyjny". Deployer:
1. Buduje paczkę `.whl`
2. Kopiuje przez SSH na RPi
3. Instaluje przez `pip` i restartuje usługę `systemd`

### Budowanie paczki Windows (Installer)
Z menedżera wybierz "Zbuduj Installer Windows". Builder generuje skrypt `.iss` i uruchamia Inno Setup (`ISCC.exe`), produkując `dist/RegisNodeSetup.exe`. Wymaga zainstalowanego Inno Setup na maszynie deweloperskiej.
