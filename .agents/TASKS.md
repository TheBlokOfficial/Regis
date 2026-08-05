# Lista Zadań Projektu Regis (TASKS)

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-05)

- [x] **Dekompozycja i Przemianowanie Nomenklatury `nodes` -> `clients`**:
  - Rozbito `controller_api.py` na podmoduły.
  - Zmieniono wszystkie ścieżki i nazwy zmiennych na `clients` / `client_id`.
  - Wdrożono Single-Step WebSocket registration po nawiązaniu połączenia.
- [x] **Wprowadzenie Klasy Bazowej Usług (`BaseService`)**:
  - Utworzono `src/client/services/base.py` dla mikrousług sidecar.
  - Zaimplementowano ujednoliconą obsługę pętli SSE i filtrowania komend.
  - Przeprowadzono refaktoryzację `llm/__main__.py`, `audio/__main__.py` oraz `satellite/__main__.py` w oparciu o `BaseService`.
- [x] **Naprawa Punktu Wejścia Klienta (`client/main.py`)**:
  - Usunięto wywołanie `fetch_config_and_register()`, opierając start w pełni na WebSocket.

---

## Zadania Przyszłe / Propozycje

- [ ] **Dalsze Testy Integracyjne End-to-End**:
  - Przetestowanie pełnego potoku mowy (STT -> LLM -> TTS) w środowisku z działającym Kontrolerem i Home Assistant.
