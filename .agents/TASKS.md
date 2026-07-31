# Lista Zadań (Task List)

Plik służy do śledzenia postępów w zaplanowanych zadaniach programistycznych i konfiguracyjnych.
Używaj konwencji: `[ ]` do zrobienia, `[/]` w trakcie, `[x]` ukończone.

---

## Aktywne Zadania

### [ARCH] Dystrybucja

- [ ] [Sesja E] Nowy system dystrybucji Windows (Regis): zbudowanie instalatora Inno Setup (`RegisNodeSetup.exe`) + Python systemowy jako prerequisite (szczegóły: `docs/distribution_rfc.md`)

### [FEATURE] Funkcje

- [ ] Migracja TTS na model Coqui XTTS v2 ("Incepcja Głosowa" / CPU)
- [ ] Integracja systemu WakeWord (oczekiwanie na paczki próbek użytkownika do modelu)
- [ ] Zaprojektowanie i wdrożenie nowej Pamięci Długoterminowej (np. wektorowej)

### [UX / Wstrzymane]

- [ ] (Wstrzymane) Wdrożenie "Checklisty Zadań" w monologach modeli, by poprawić zdolności analityczne na wzór Scratchpadu.

---

## Zarchiwizowane (Historia Sesji)

Poniżej skrócone podsumowanie kategorii ukończonych prac. Szczegółowa historia dostępna w `git log`.

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
