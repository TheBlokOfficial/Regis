# Dokument Architektoniczny: Restrukturyzacja Regis do Dwóch Usług

> **Ten dokument jest instrukcją dla agenta implementującego.** Opisuje decyzje podjęte
> w sesji architektonicznej z użytkownikiem. Nie zawiera kodu — zawiera precyzyjną wizję
> tego co ma powstać i dlaczego.

---

## 1. Kontekst — Dlaczego Restrukturyzacja

Projekt składa się aktualnie z 7 pakietów w `src/`:
`core`, `integrations`, `controller`, `controller.worker`, `regis_satellite`, `regis_terminal`, `regis_cli`.

Zidentyfikowano dwa strukturalne problemy:

**Problem 1 — Fragmentacja Windows.** Trzy osobne binarki (`controller.worker`, `regis_satellite`,
`regis_terminal`) trafiają na ten sam PC. Użytkownik musiałby uruchamiać trzy osobne procesy,
trzy `.bat`, trzy konfiguracje. Brak koordynacji i wspólnego UX.

**Problem 2 — Monolityczność plików.** `controller/main.py` (361 linii) zawiera jednocześnie:
logikę rejestru workerów, logikę rejestru satelit, heartbeat, proxy SSE tekstu, proxy SSE audio,
endpoint narzędzi — to pięć odrębnych odpowiedzialności w jednym pliku.

**Cel restrukturyzacji:** Skonsolidować do dwóch usług produkcyjnych o jasnych granicach,
zachowując bez zmian warstwę protokołu (HTTP/SSE), logikę Rejestru Encji, Spatial Context
Filtering i wszystkie inne rozstrzygnięte decyzje z `MANIFEST.md`.

---

## 2. Wizja Docelowa — Dwie Usługi

### Usługa 1: `controller` (Raspberry Pi 5, Linux)

- Rola: bez zmian względem `MANIFEST.md §3.1`
- Dystrybucja: wyłącznie `.whl` na Linux (pip install). Brak wersji Windows.
- Zmiana w tej restrukturyzacji: **tylko wewnętrzna** — rozbicie monolitycznego `main.py`
  na podmoduły bez żadnej zmiany API.

### Usługa 2: `node` (Windows PC, System Tray App)

Nowy pakiet zastępujący `controller.worker` + `regis_satellite` + `regis_terminal`.

Jest to aplikacja desktopowa Windows działająca jako **ikona w System Tray** (prawy dolny róg
paska zadań, obok zegara — identycznie jak Dropbox, Discord, antywirus).

**Kluczowe właściwości:**
- Worker i Satellite to **procesy w tle** bez własnych okien (niewidoczne w pasku zadań,
  widoczne tylko w Menedżerze Zadań) — zarządzane przez tray app przez `subprocess.Popen`
  z flagą `CREATE_NO_WINDOW`
- Worker i Satellite mogą działać **jednocześnie** na tym samym PC — nie wykluczają się
- Panel (tray app) można zamknąć bez zabijania procesów działających w tle
- Autostart rejestrowany przez sam panel (klucz Registry `HKCU\...\Run`) — użytkownik
  włącza/wyłącza z menu tray

---

## 3. Flow Użytkownika (node)

### Pierwsze uruchomienie (brak `data/settings.json`)

```
Uruchom.bat
  → node.exe uruchamia krótką konsolę z wizardem
  → Wizard (questionary) pyta o:
      - Nazwa tej instancji / Worker ID  (np. "Mój Gaming PC")
      - Pokój (room)                     (np. "salon")
      - URL Kontrolera                   ("auto" = UDP discovery, lub ręczny)
      - Tier modelu LLM                  (butler / regis / prime)
      - Które usługi uruchamiać          (Worker / Satellite / obie)
  → Zapisuje do data/settings.json
  → Konsola znika — pojawia się ikona w System Tray
```

### Każde kolejne uruchomienie

```
Uruchom.bat
  → node.exe czyta data/settings.json
  → Ikona pojawia się w System Tray (bez konsoli)
  → Automatycznie uruchamia usługi zdefiniowane w ustawieniach
```

### Interakcja przez System Tray (prawy klik na ikonę)

```
Regis Node — [nazwa instancji]
──────────────────────────────
Worker LLM:   Uruchomiony    [Zatrzymaj]
Satellite:    Zatrzymany     [Uruchom]
──────────────────────────────
Autostart przy logowaniu: [Włącz/Wyłącz]
Konfiguracja...                    ← otwiera ponownie konsolę z wizardem
──────────────────────────────
Zamknij panel (procesy działają)
Zamknij wszystko
```

**Stan ikony:** Ikona tray może wizualnie sygnalizować stan (np. kolor/wariant ikony).
Szczegóły implementacji pozostawia się agentowi.

---

## 4. Nowa Struktura Pakietów

```
src/
├── core/                   ← biblioteka wspólna [BEZ ZMIAN]
├── integrations/           ← klient HA          [BEZ ZMIAN]
│
├── controller/       ← usługa RPi5        [REFAKTORYZACJA WEWNĘTRZNA]
│   ├── __init__.py
│   ├── main.py             ← entry point (uruchamia uvicorn, ~20 linii)
│   ├── app.py              ← instancja FastAPI + lifespan
│   ├── registry.py         ← logika rejestrów: workerów i satelit + heartbeat
│   ├── router.py           ← proxy SSE: chat tekstowy + chat audio + failover
│   └── tools.py            ← endpoint /v1/tools/execute
│
├── node/             ← usługa Windows     [NOWY PAKIET]
│   ├── __init__.py
│   ├── main.py             ← entry point: wizard lub tray (zależnie od settings.json)
│   ├── tray.py             ← logika System Tray (pystray)
│   ├── wizard.py           ← kreator konfiguracji (questionary), otwierany też z tray
│   ├── worker.py           ← logika Worker: przeniesiona z controller/worker/server.py
│   ├── node.py             ← logika węzła: przeniesiona z controller/worker/node.py
│   └── satellite.py        ← logika Satellite: przeniesiona z regis_satellite/main.py
│
├── regis_cli/              ← menedżer projektu  [AKTUALIZACJA BUILDERA]
│   ├── __init__.py
│   ├── main.py
│   ├── builders.py         ← buduje 1 paczkę (node) zamiast 3
│   ├── deployers.py
│   └── ux.py
│
└── [controller/worker/]         ← DO USUNIĘCIA po migracji
    [regis_satellite/]      ← DO USUNIĘCIA po migracji
    [regis_terminal/]       ← DO USUNIĘCIA po migracji (patrz §5)
```

---

## 5. Status `regis_terminal` — Decyzja

`regis_terminal` w obecnym kształcie (tekstowy klient-chatbot) jest przestarzały i
wychodzi z użycia.

**Nowa koncepcja Terminala** to narzędzie developerskie do monitorowania systemu — pokazuje
aktywne sesje, zarejestrowane węzły, satelity, logi z Kontrolera. Jest to **osobny skrypt/pakiet**,
nie dystrybuowany w paczce użytkownika (nie wchodzi do `node`).

**Priorytet: niski.** Terminal jest narzędziem wygodnym, ale nieblokującym. Implementacja
`node` jest absolutnym priorytetem. Terminal może być zrealizowany w osobnej sesji.
Można go potencjalnie zintegrować z `regis_cli` jako dodatkowy tryb diagnostyczny.

**Działanie dla agenta:** Stary kod `regis_terminal` można zachować w repozytorium jako
punkt odniesienia, ale nie musi być migrowany. Nowa implementacja terminala (jeśli w ogóle)
powstanie od zera w osobnej sesji.

---

## 6. Nowe Zależności (`pyproject.toml`)

Nowy pakiet `node` wymaga dopisania do opcjonalnych zależności:

```toml
[project.optional-dependencies]
node = [
    "pystray>=0.19.5",        # System Tray (ikona + menu)
    "pillow>=10.0.0",         # Wymagane przez pystray do ikon
    "faster-whisper>=1.0.0",  # STT (przeniesione z [worker])
    "sounddevice>=0.4.6",     # Audio in (przeniesione z [satellite])
    "soundfile>=0.12.1",      # Audio format (przeniesione z [satellite])
    "numpy>=1.26.0",
    "fastapi>=0.111.0",       # Serwer HTTP dla Worker API
    "uvicorn>=0.30.1",
    "pydantic>=2.7.4",
    "python-multipart>=0.0.9",
]
```

Stare extras `[worker]` i `[satellite]` mogą zostać usunięte lub zostawione jako aliasy
(decyzja agenta na podstawie tego czy coś je jeszcze referuje).

Nowy entry point:
```toml
[project.scripts]
regis-node = "node.main:main"
```

---

## 7. Format Paczki Portable (dist/)

Builder w `regis_cli/builders.py` produkuje **jedną** paczkę zamiast trzech:

```
dist/
└── Regis-Node/
    ├── Uruchom.bat          ← uruchamia system\regis-node.exe
    ├── data/
    │   └── settings.json    ← tworzony przez wizard przy pierwszym uruchomieniu
    └── system/
        └── regis-node/      ← binarka PyInstaller (--onedir)
            └── regis-node.exe
```

`settings.json` w paczce portable (przykład po przejściu wizarda):
```json
{
    "instance_name": "Mój Gaming PC",
    "room": "salon",
    "controller_url": "auto",
    "active_tier": "regis",
    "worker_port": 8001,
    "worker_host": "0.0.0.0",
    "autostart_worker": true,
    "autostart_satellite": false
}
```

`Uruchom.bat` uruchamia `regis-node.exe` bez okna konsoli (parametr `/B` lub `start /B`)
— konsola pojawia się tylko gdy wizard jest aktywny.

---

## 8. Plan Sesji Implementacyjnych

> **Ważne:** Każda sesja powinna kończyć się przechodzącymi testami. Nie rozpoczynaj
> kolejnej sesji jeśli poprzednia zostawiła projekt w niestabilnym stanie.

### Sesja A — Sprzątanie i weryfikacja bazy (mała, ~1h)

Cel: Upewnić się że baza jest stabilna przed restrukturyzacją.

1. Sprawdzić czy `regis_satellite/` ma `__init__.py` — jeśli nie, dodać
2. Sprawdzić czy `regis_terminal/` istnieje w `src/` (nie widoczny na liście pakietów)
3. Uruchomić `pytest` — zarejestrować bazowy wynik (ile testów przechodzi)
4. Przejrzeć `pyproject.toml` entry points — upewnić się że wszystko się buduje

### Sesja B — Refaktoryzacja `controller` (średnia, ~2h)

Cel: Rozbić `main.py` (361 linii) na 4 podmoduły. **Zero zmian w API.**

Kolejność:
1. Wydzielić `registry.py` — klasy/funkcje: `worker_registry`, `satellite_registry`,
   `_heartbeat_loop`, `_pick_worker`, endpointy `/v1/workers/*`, `/v1/satellites/*`
2. Wydzielić `tools.py` — endpoint `/v1/tools/execute`
3. Wydzielić `router.py` — `_proxy_sse_to_queue`, `_proxy_audio`, endpointy `/v1/chat/*`,
   `/v1/clear_history`
4. Stworzyć `app.py` — instancja FastAPI, lifespan, import routerów FastAPI (APIRouter)
5. `main.py` staje się ~20-linijkowym entry pointem (tylko `start()` wywołujące uvicorn)

Weryfikacja: `pytest` musi przejść identycznie jak przed sesją.

### Sesja C — Stworzenie `node` (duża, ~4h)

Cel: Nowy pakiet Windows zastępujący trzy stare.

Kolejność:
1. Stworzyć `src/node/` z plikami `__init__.py`, `main.py`, `tray.py`, `wizard.py`,
   `worker.py`, `node.py`, `satellite.py`
2. Przenieść logikę `controller/worker/node.py` → `node/node.py`
3. Przenieść logikę `controller/worker/server.py` → `node/worker.py`
4. Przenieść logikę `regis_satellite/main.py` → `node/satellite.py`
5. Napisać `wizard.py` — formularz questionary zapisujący `settings.json`
6. Napisać `tray.py` — ikona pystray, menu, zarządzanie procesami przez `subprocess.Popen`
7. Napisać `main.py` — logika: jeśli brak `settings.json` → wizard, potem → tray
8. Zaktualizować `pyproject.toml` (extras `[node]`, entry point `regis-node`)
9. Zaktualizować `regis_cli/builders.py` — jedna paczka zamiast trzech

Weryfikacja: Uruchomić `regis-node` lokalnie — przejść wizard, sprawdzić czy ikona pojawia
się w tray, sprawdzić czy Worker rejestruje się w Kontrolerze.

### Sesja D — Dokumentacja i czyszczenie (mała, ~1h)

Cel: Zamknąć restrukturyzację.

1. Usunąć (lub oznaczyć jako deprecated) stare pakiety: `controller/worker/`, `regis_satellite/`,
   `regis_terminal/`
2. Zaktualizować `docs/ONBOARDING.md` — nowa struktura pakietów
3. Zaktualizować `MANIFEST.md §3` — opisać że Windows PC = `node` (worker+satellite)
4. Uruchomić pełne `pytest` — zielone
5. Zbudować paczkę testową (`regis.bat` → build portable) — sprawdzić strukturę `dist/`

---

## 9. Decyzje Podjęte w Tej Sesji (Nie Otwieraj Ponownie)

| Decyzja | Szczegół |
|---|---|
| Windows = tray app | `node` to ikona System Tray, nie CLI |
| Worker + Satellite jednocześnie | Nie wykluczają się — oba mogą działać na tym samym PC |
| Ukryte procesy | Worker i Satellite jako `subprocess.Popen` z `CREATE_NO_WINDOW` |
| Autostart przez Registry | `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` |
| Konfiguracja: wizard + edycja z tray | Questionary, zapisuje `settings.json` |
| Kontroler tylko Linux | `.whl`, bez wersji Windows — bez zmian |
| Terminal: niski priorytet | Stara wersja przestarzała, nowa (monitor) — osobna sesja |
| Pystray jako biblioteka tray | Nowa zależność w extras `[node]` |

---

## 10. Co Absolutnie Nie Ulega Zmianie

- Protokół komunikacji Controller ↔ Worker ↔ Satellite (HTTP + SSE) — bez zmian
- Rejestr Encji, Continuous Registration, Heartbeat — bez zmian
- Spatial Context Filtering — bez zmian
- Auto-Discovery (UDP Broadcast) w `core/discovery.py` — bez zmian
- `core/` i `integrations/` — bez zmian
- Wszystkie decyzje LLM z tabeli w `AGENT_GUIDE.md` — bez zmian
- Format `.whl` dla RPi5 — bez zmian
