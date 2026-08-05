# Lista Zadań Projektu Regis (TASKS)

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-05)

- [x] **Dekompozycja i Przemianowanie Nomenklatury `nodes` -> `clients`**:
  - Rozbito `controller_api.py` na podmoduły.
  - Zmieniono wszystkie ścieżki i nazwy zmiennych na `clients` / `client_id`.
  - Wdrożono Single-Step WebSocket registration po nawiązaniu połączenia.
- [x] **Wprowadzenie Klasy Bazowej Usług (`BaseService`)**:
  - Utworzono `src/client/services/base.py` dla mikrousług sidecar.
  - Zaimplementowano ujednoliconą obsługę pętli SSE i filtrowania komend.
  - Przeprowadzono refaktoryzację `ollama_worker/__main__.py`, `audio/__main__.py` oraz `satellite/__main__.py` w oparciu o `BaseService`.
- [x] **Przemianowanie Usługi `llm` na `ollama_worker` oraz Refaktoryzacja `engine.py`**:
  - Wypłaszczono strukturę pętli generującej strumień w `engine.py`.
  - Zaktualizowano nazwy we wszystkich rejestrach, menadżerach i schematach.
- [x] **Inicjalizacja Self-Healing i Maszyna Stanów w `ollama_worker`**:
  - Utworzono 3-stanową maszynę stanów (`INITIALIZING`, `READY`, `BUSY`).
  - Wdrożono pętlę wyczekiwania na Ollamę bez wyłączania procesu przy starcie.
  - Dodano obsługę błędów komunikacji (zrzucanie do `INITIALIZING`) oraz Dynamic Model Swapping.
- [x] **Protokół Graceful Shutdown i Rozdzielenie Schematów IPC**:
  - Utworzono `src/client/ipc_schemas.py` z `SystemCommand` (`STOP`, `SHUTDOWN`).
  - Wdrożono obsługę `stop()` w `BaseService` i automatyczne uwalnianie pamięci VRAM przez `ollama_worker`.
  - Wdrożono wyczekiwanie i bezpieczne zatrzymywanie w `ProcessManager._stop_service()`.
  - Dodano `SetConsoleCtrlHandler` w `src/client/main.py` dla przycisku `[X]` okna konsoli w Windowsie.

---

## Zadania Przyszłe / Propozycje

- [ ] **Dalsze Testy Integracyjne End-to-End**:
  - Przetestowanie pełnego potoku mowy (STT -> LLM -> TTS) w środowisku z działającym Kontrolerem i Home Assistant.
