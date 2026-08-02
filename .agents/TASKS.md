# Lista Zadań (Task List)

Plik służy do śledzenia postępów w zaplanowanych zadaniach programistycznych i konfiguracyjnych.
Używaj konwencji: `[ ]` do zrobienia, `[/]` w trakcie, `[x]` ukończone.

---

## Aktywne Zadania

### [INFRA / HARDWARE]
- [ ] Migracja Kontrolera i Workera na nową stację Minisforum UM760 Slim (x86_64, Ryzen 5 7640HS) po jej otrzymaniu przez Użytkownika (~10 dni)
- [ ] **[EMBEDDED FALLBACK]** Implementacja in-process fallback parsera w Kontrolerze: gdy `worker_registry` pusty i chmura pada → zamiast `return None` w `providers.get_llm_backend()`, wywołać lokalny parser bezpośrednio (bez HTTP). Realizować dopiero na Minisforum — RPi5 jest zbyt słaby. Patrz `src/controller/providers.py`.

### [ARCH] Dystrybucja

- [ ] [Sesja E] Nowy system dystrybucji Windows (Regis): zbudowanie instalatora Inno Setup (`RegisNodeSetup.exe`) + Python systemowy jako prerequisite (szczegóły: `docs/distribution_rfc.md`)

### [DEV / TYMCZASOWE]

- [ ] **[WORKER PROFILE SWAP]** Mechanizm ręcznego przełączania modelu workera na desktopie Windows między trybem Butler (mały model, `tier=butler`, testowanie ścieżki fallback) a trybem Regis (model 9B, `tier=regis`, zastępstwo chmury). Propozycja implementacji: dwa profile `.env` (`settings.worker.butler.env` / `settings.worker.regis.env`) + komenda CLI lub skrypt restartujący workera z wybranym profilem. Zadanie tymczasowe — traci sens po dostarczeniu Minisforum i wdrożeniu embedded fallback.

### [FEATURE / ARCH] Wdrożenie Zjednoczonego Węzła (Node-Centric Architecture)

- [x] **[NODE-CENTRIC — Etap 1]** Schematy & Rejestr: `src/protocol/schemas.py` (`NodeRegistrationRequest`), `src/controller/registry.py` (`node_registry`), `src/controller/routers/nodes.py` (`/v1/nodes/register`).
- [x] **[NODE-CENTRIC — Etap 2]** Menedżer Węzła PC: `src/node/service.py` (zbiorcza rejestracja `services: ["worker", "satellite"]` i wyrejestrowywanie całej maszyny).
- [x] **[NODE-CENTRIC — Etap 3]** Routing i Heartbeat: `src/controller/services/chat_service.py` (routing do Węzła), `src/controller/routers/ui.py` (odbiór `POST /api/node/event`), heartbeat na porcie 8099.
- [x] **[NODE-CENTRIC — Etap 4]** Reaktywny Web UI: `src/controller/web/` (unifikacja kart w "Węzły Systemowe" z połączonym podglądem modeli LLM oraz VAD Satelity).
- [x] **[NODE-CENTRIC — Etap 5]** Testy, Weryfikacja i Deployment: Uruchomienie `pytest`, testy manualne `service.bat` i wysłanie aktualizacji Kontrolera na Raspberry Pi.
- [x] **[NODE REFACTORING — Async & BaseSubservice]**: Usunięcie `node.py` (God Object), migracja `worker.py` i `ollama.py` na `httpx.AsyncClient` + AsyncGenerators, dodanie `argparse` z CLI flags oraz wdrożenie obiektowej klasy bazowej `BaseSubservice` dla dynamicznego zarządzania subprocesami w `process_manager.py`.

### [FEATURE] Web UI (Reaktywny Panel Kontrolny & Optymalizacja UX)

- [x] **[WEB UI — Faza 1]** Backend Kontrolera: stworzenie `src/controller/event_bus.py` + router `src/controller/routers/ui.py` (endpointy `/api/events` SSE, `/api/status`, `/api/node/{id}/command`). Rejestracja w `app.py` PRZED `StaticFiles`. Szczegóły: `docs/web_ui_rfc.md` §5.
- [x] **[WEB UI — Faza 2]** Frontend: `src/controller/web/` (index.html, style.css, app.js). Reaktywny panel z kartami węzłów, satelit i dziennikiem zdarzeń na żywo. Szczegóły: `docs/web_ui_rfc.md` §7.
- [x] **[WEB UI — Refactoring]** Rozbicie monolitycznego `app.js` (448 linii) na 5 modułów ES: `utils.js`, `state.js`, `renderer.js`, `events.js`, `api.js`. Natywne ES Modules (bez bundlera), `app.js` jako orchestrator (~20 linii). Jedyna zmiana w `index.html`: `type="module"` na `<script>`.
- [x] **[WEB UI — Faza 3]** Satelita pushuje zdarzenia do Kontrolera (`POST /api/satellite/event`). Modyfikacja `src/node/satellite.py`. Szczegóły: `docs/web_ui_rfc.md` §6.2.
- [x] **[WEB UI — Faza 4]** Integracja System Tray: akcja "Otwórz Dashboard" otwiera przeglądarkę (`webbrowser.open()`). Usunięcie `src/node/dashboard.py`. Szczegóły: `docs/web_ui_rfc.md` §6.3.
- [x] **[WEB UI — UX Refinement & Modern Layout]** Restrukturyzacja układu Pulpitu do zbalansowanego widoku trójkolumnowego (`Węzły` | `Dostawcy LLM` | `Integracje`) o równych proporcjach `repeat(3, minmax(0, 1fr))`, wycentrowane wąskie kafelki statusowe, 10% marginesy boczne, stałe wysokości kontenerów z wewnętrznym scrollowaniem, ustandaryzowanie i przefiltrowanie Dziennika Zdarzeń (`[INFO]`/`[OFFLINE]`/`[ERROR]`), usunięcie szumów VAD z badge'y i usunięcie zaszłości portu 8099.

### [FEATURE] Web UI — Wielosesyjność & Dedykowana Zakładka Czatu

- [x] **[FAZA 1 — Backend: Słownik Sesji per Satelita]**: Refaktoryzacja `src/controller/registry.py` (zamiana `conversation_history` na `conversation_sessions: dict[str, list[dict]]`), obsługa `satellite_id` / `room` w `src/controller/services/chat_service.py` oraz dodanie endpointu `/v1/sessions` w `src/controller/routers/chat.py`.
- [x] **[FAZA 2 — Frontend: Nawigacja Zakładkowa & Wygląd Czatu]**: Modyfikacja `src/controller/web/index.html` i `style.css` (przełącznik `Dashboard` / `Czat & Konwersacje`, stylizacja bąbelków czatu `.msg-bubble`, kontenera `#chat-messages` oraz paska wpisywania).
- [x] **[FAZA 3 — Frontend: Moduł Czatu & Strumieniowanie]**: Utworzenie `src/controller/web/chat.js` (zarządzanie zakładkami, podłączanie pod wybraną Satelitę z menu rozwijanego, wysyłanie wiadomości pod `POST /v1/chat/stream` z wybranym `satellite_id` i `room`, czyszczenie historii `/v1/clear_history`).
- [x] **[FAZA 4 — Frontend: Integracja SSE & Przestrzeń Wirtualna]**: Aktualizacja `src/controller/web/events.js` i `app.js` (reagowanie na `conversation_turn` per sesję, automatyczne przełączanie kontekstu i auto-scroll do dna).
- [x] **[FAZA 5 — Testy, Weryfikacja i Deployment]**: Uruchomienie testów `pytest`, wdrożenie na Raspberry Pi (`build_controller.py`), test wirtualnego pisania z kontekstem Łazienki/Salonu w przeglądarce i zapis w Git.

### [FEATURE] Funkcje

- [x] **[NLU / STABILITY]** Naprawa pętli awarii workera RPi5, usunięcie przestarzałego `regis-stt.service`, wdrożenie oficjalnego `format: json` w Ollamie i przywrócenie profilera czasowego w NLU
- [ ] Migracja TTS na model Coqui XTTS v2 ("Incepcja Głosowa" / CPU)
- [ ] Integracja systemu WakeWord (oczekiwanie na paczki próbek użytkownika do modelu)
- [ ] Zaprojektowanie i wdrożenie nowej Pamięci Długoterminowej (np. wektorowej)
- [x] **[ARCH — Phase 1]** Restrukturyzacja pod system providerów LLM: `llm_backends/`, OpenRouter, refaktoryzacja routera (Zrealizowano - zarchiwizowano)
- [ ] **[ARCH — Phase 2]** Abstrakcja STT/TTS backends + split audio pipeline w Kontrolerze (cloud STT/TTS bez Windows Node)

---

## Zarchiwizowane (Historia Sesji)

### Refaktoryzacja Modułu Node: Async, Brak God Object & BaseSubservice (Sierpień 2026)
Przeprowadzono gruntowne unowocześnienie i usprawnienie architektury modułu `src/node/`:
1. **Usunięto `node.py`** – wyeliminowano przerośniętą klasę `WorkerNode` na rzecz bezpośredniego instancjonowania silników w `worker.py`.
2. **Przejście na `httpx.AsyncClient` i AsyncGenerator** – zastąpiono blokujące zapytania HTTP i wątki generatorami asynchronicznymi w `LLMEngine` i backendzie Ollamy.
3. **Usunięcie Split-Brain** – dodano `argparse` w `worker.py` oraz `satellite.py`, a `process_manager.py` przekazuje parametry bezpośrednio w poleceniach CLI.
4. **Obiektowy `BaseSubservice`** – stworzono klasę bazową dla podprocesów oraz rejestr `SERVICES`. Uporządkowano zamykanie procesów (`stop_all_services()`), wyrejestrowywanie oraz raportowanie statusu przez WebSocket.
5. Wynik: 34/34 testy pytest przechodzą.

### Pełna Izolacja Usług — Restrukturyzacja `src/protocol/` (Sierpień 2026)
Przeprowadzono gruntowną reorganizację monorepo. Folder `src/protocol/` jest teraz chudym kontraktem sieciowym zawierającym wyłącznie `discovery.py` i `schemas.py` (klasy rejestracyjne). Wykonane kroki:
1. Silniki (`llm_engine`, `stt_engine`, `tts_engine`, `stream_parser`) przeniesione z `protocol/` do `src/node/engines/` i `src/worker/engines/`.
2. `history_utils.py` przeniesiony do `src/node/` i `src/worker/`.
3. `llm_backends/` przeniesiony do `src/controller/llm_backends/`; własne kopie dodane do `src/node/llm_backends/` i `src/worker/llm_backends/`.
4. `config.py`, `logger.py`, `exceptions.py` zduplikowane do każdej usługi i usunięte z `protocol/`.
5. `BASE_TOOLS_SCHEMA` przeniesiony do `src/controller/schemas_tools.py`.
6. Audyt QA wykrył i naprawiono 2 cross-importy (`controller→node`, `worker→node`) i 1 zestarzały import w testach.
Wynik: zero cross-importów, 34/34 testów przechodzi.

### Refaktoryzacja LLM Backends (historycznie — wchłonięta przez restrukturyzację protocol/)
Wyczyszczono katalog `protocol/` z komponentów `llm_backends/` (przeniesiono do `src/controller/llm_backends/`). Zaktualizowano wszystkie importy.

### Refaktoryzacja UX Web UI & Layout 16:9 (Sierpień 2026)
Przeprowadzono gruntowną optymalizację ergonomii i estetyki panelu kontrolnego.

### Optymalizacja NLU i Diagnostyki (RPi5)
Naprawiono błędy parsowania JSON przy modelach z funkcją myślenia (`qwen3`).

### Architektura i Restrukturyzacja
Ukończono pełną restrukturyzację monorepo do układu `src/` z trzema usługami produkcyjnymi.
