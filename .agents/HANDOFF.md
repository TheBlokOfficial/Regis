# HANDOFF: Stan Projektu Regis

## 1. Wykonane Prace w Ostatniej Sesji (2026-08-05)

- **Zmiana Nomenklatury Usługi `llm` na `ollama_worker`**:
  - Przemianowano całą usługę z misleading nazwy `llm` na `ollama_worker` w rejestrach, schematach protokołu, menadżerze procesów oraz orkiestratorze.
  - Refaktoryzacja i wypłaszczenie 7-piętrowej logiki w `engine.py` w funkcji `generate_response_stream` (oddelegowanie do `_process_stream`).

- **Samoleczenie (Self-Healing) i Maszyna Stanów w `ollama_worker`**:
  - Utworzono moduł [`src/client/services/ollama_worker/states.py`](file:///d:/Projekty/Regis/src/client/services/ollama_worker/states.py) z 3 zunifikowanymi stanami dyspozycyjności (`INITIALIZING`, `READY`, `BUSY`).
  - Usunięto brutalne `sys.exit(1)` przy braku Ollamy na starcie. Usługa w stanie `INITIALIZING` asynchronicznie wyczekuje w tle pętlą `_ensure_ready_loop` na podniesienie Ollamy, wczytuje model w VRAM i płynnie przechodzi do `READY`.
  - Dowolna awaria sieciowa w trakcie wnioskowania odsyła błąd do Kontrolera i przestawia usługę z powrotem do `INITIALIZING` (samoleczenie).
  - Wdrożono **Dynamic Model Swapping**: żądanie innego modelu niż w VRAM wyładowuje obecny, wraca do `INITIALIZING` i wgrywa żądany model.

- **Protokół Łagodnego Zamykania (Graceful Shutdown)**:
  - Rozszerzono [`src/client/services/base.py`](file:///d:/Projekty/Regis/src/client/services/base.py) o metodę `async def stop(self)` oraz automatyczną obsługę sygnałów zamykania z magistrali.
  - Zaktualizowano `OllamaWorkerService.stop()`, aby wysyłała HTTP POST z `keep_alive: 0` do Ollamy, zwalniając VRAM z karty GPU przed wyłączeniem podprocesu.
  - Przebudowano `ProcessManager._stop_service()` ([`src/client/process_manager.py`](file:///d:/Projekty/Regis/src/client/process_manager.py)), aby najpierw wysyłał polecenie zamknięcia przez magistralę `service_bus` i dawał podprocesowi czas na samoistne posprzątanie przed ewentualnym `terminate()`.
  - Dodano przechwytywacz Windows `SetConsoleCtrlHandler` w [`src/client/main.py`](file:///d:/Projekty/Regis/src/client/main.py), zapewniający prawidłowe uruchomienie `quit_all()` nawet przy zamknięciu okna terminala przyciskiem `[X]`.

- **Czysta Architektura i Rozdzielenie Schematów Protokołu**:
  - Rozdzielono komendy sieciowe Kontrolera od wewnętrznych komend cyklu życia klienta.
  - Utworzono nowy plik **[`src/client/ipc_schemas.py`](file:///d:/Projekty/Regis/src/client/ipc_schemas.py)** zawierający `SystemCommand` (`STOP`, `SHUTDOWN`).
  - Plik **[`src/protocol/schemas.py`](file:///d:/Projekty/Regis/src/protocol/schemas.py)** pozostał 100% czysty i dedykowany wyłącznie publicznemu protokołowi Kontroler <-> Klient.

---

## 2. Aktualny Stan Kodu

- **`ollama_worker` (`src/client/services/ollama_worker/`)**:
  - `__main__.py`: Pętla samolecząca, 3 stany (`OllamaWorkerState`), obsługa `SystemCommand.STOP` i uwalnianie VRAMu.
  - `ollama_client.py`: Bezpieczne wywołania `preload_model`, `unload_model`, `ensure_model_exists`.
- **Zarządzanie Procesami i Magistrala**:
  - `src/client/process_manager.py`: Generyczny zarządca procesów wysyłający `SystemCommand.STOP` przez `service_bus`.
  - `src/client/ipc_schemas.py`: Wewnętrzne Enumy dla procesów klienckich.
  - `src/protocol/schemas.py`: Czysty protokół SIECIOWY Kontrolera.

---

## 3. Kroki Startowe dla Następnego Agenta

1. Obowiązkowo zapoznaj się z [`docs/MANIFEST.md`](file:///d:/Projekty/Regis/docs/MANIFEST.md) oraz [`docs/AGENT_GUIDE.md`](file:///d:/Projekty/Regis/docs/AGENT_GUIDE.md).
2. Sprawdź status zadań w [`.agents/TASKS.md`](file:///d:/Projekty/Regis/.agents/TASKS.md).
3. Przeprowadź testy integracyjne end-to-end z Kontrolerem i Satelitą przy włączonej obsłudze wnioskowania przez `ollama_worker`.
