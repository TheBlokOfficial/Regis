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

### [FEATURE] Web UI (Reaktywny Panel Kontrolny)

- [x] **[WEB UI — Faza 1]** Backend Kontrolera: stworzenie `src/controller/event_bus.py` + router `src/controller/routers/ui.py` (endpointy `/api/events` SSE, `/api/status`, `/api/node/{id}/command`). Rejestracja w `app.py` PRZED `StaticFiles`. Szczegóły: `docs/web_ui_rfc.md` §5.
- [ ] **[WEB UI — Faza 2]** Frontend: `src/controller/web/` (index.html, style.css, app.js). Reaktywny panel z kartami węzłów, satelit i dziennikiem zdarzeń na żywo. Szczegóły: `docs/web_ui_rfc.md` §7.
- [ ] **[WEB UI — Faza 3]** Satelita pushuje zdarzenia do Kontrolera (`POST /api/satellite/event`). Modyfikacja `src/node/satellite.py`. Szczegóły: `docs/web_ui_rfc.md` §6.2.
- [ ] **[WEB UI — Faza 4]** Integracja System Tray: akcja "Otwórz Dashboard" otwiera przeglądarkę (`webbrowser.open()`). Usunięcie `src/node/dashboard.py`. Szczegóły: `docs/web_ui_rfc.md` §6.3.

### [FEATURE] Funkcje

- [x] **[NLU / STABILITY]** Naprawa pętli awarii workera RPi5, usunięcie przestarzałego `regis-stt.service`, wdrożenie oficjalnego `format: json` w Ollamie i przywrócenie profilera czasowego w NLU
- [ ] Migracja TTS na model Coqui XTTS v2 ("Incepcja Głosowa" / CPU)
- [ ] Integracja systemu WakeWord (oczekiwanie na paczki próbek użytkownika do modelu)
- [ ] Zaprojektowanie i wdrożenie nowej Pamięci Długoterminowej (np. wektorowej)
- [x] **[ARCH — Phase 1]** Restrukturyzacja pod system providerów LLM: `llm_backends/`, OpenRouter, refaktoryzacja routera (szczegóły: `docs/llm_providers_rfc.md`)
- [ ] **[ARCH — Phase 2]** Abstrakcja STT/TTS backends + split audio pipeline w Kontrolerze (cloud STT/TTS bez Windows Node)

### [UX / Wstrzymane]

- [ ] (Wstrzymane) Wdrożenie "Checklisty Zadań" w monologach modeli, by poprawić zdolności analityczne na wzór Scratchpadu.

---

## Zarchiwizowane (Historia Sesji)

Poniżej skrócone podsumowanie kategorii ukończonych prac. Szczegółowa historia dostępna w `git log`.

### Optymalizacja NLU i Diagnostyki (RPi5)
Naprawiono błędy parsowania JSON przy modelach z funkcją myślenia (`qwen3`), zastępując Prefix Injection natywnym parametrem `"format": "json"` w Ollama API. Wyczyszczono zdeprecjonowane usługi systemd (`regis-stt.service`). Zintegrowano profiler `on_profiler` w `nlu_agent.py` i przywrócono pełne statystyki czasu wykonania w stopce CLI (`TTFT`, `Gen`, `Narzędzia`). Przestawiono domyślny model Butlera na `qwen2.5:0.5b`.

### Architektura i Restrukturyzacja
Ukończono pełną restrukturyzację monorepo do układu `src/` z trzema usługami produkcyjnymi (`controller`, `controller.worker`, `node`). Rozwiązano dług dystrybucyjny — system `.whl` dla RPi5 i Portable App dla Windows. Wdrożono Auto-Discovery (UDP Broadcast Zero-Conf). Wdrożono Rejestr Encji (Satelity i Węzły), Spatial Context Filtering, Continuous Registration. Przeprowadzono pełny re-branding kodu na "Regis".

### LLM i Prompt Engineering
Przejście przez kolejne generacje modeli: 7B → 3B → 1.5B (Butler NLU) oraz 7B → 14B → 9B (ReAct Agent). Wdrożono architekturę "Droga A" (narzędzia jako XML w prompcie, bez natywnego `tools` API Ollamy). Stop token `</action>`. Pętla ReAct ze `<thought>` i streamingiem. Structured Outputs (JSON Schema) dla Butlera. Naprawiono halucynacje, few-shot poisoning, amnezję przy długich sesjach.

### Audio i Satelita
Wdrożono STT (Whisper/faster-whisper) scentralizowane na węźle. WakeWord (openwakeword). VAD energetyczny. TTS. Natywny feedback dźwiękowy Windows. Inteligentne filtrowanie czasowe i auto-amnezja bufora.

### UX i CLI
Monitor konwersacji (SSE). Refaktoryzacja traya na `service.py` z HTTP API. Dashboard jako klient HTTP. Live Dashboard (Monitor Głosowy). Pętla REPL z infinite scrolling. Unifikacja wizualna (rich, questionary).

### Integracje HA
Narzędzia `get_device_state`, `execute_action`, `get_current_time`, `get_weather`. Wirtualne Grupy, aliasy. Zabezpieczenie przed urządzeniami `unavailable`. Toggle, logika jasności. Spatial Context (filtrowanie urządzeń per pokój). Pobieranie stanu baterii telefonu (z tłumaczeniem stanów bezpośrednio w warstwie integracji).

### Debugowanie i Obserwowalność
Wdrożono system logowania warstwy I/O (`core/logger.py`). Logi DEBUG trafiają do `logs/<usługa>_YYYY-MM-DD.log` (FileHandler), konsola pozostaje na INFO. Pokryte: żądania HTTP do HA (przed/po `state_mapping`), iteracje pętli ReAct (TTFT, czas, rozmiar kontekstu), ciche błędy NLU (`JSONDecodeError`), decyzje routingowe Kontrolera, timeouty węzłów.
