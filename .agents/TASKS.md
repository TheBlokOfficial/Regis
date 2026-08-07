# Lista Zadań Projektu Regis (TASKS)

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-07)

- [x] **Refaktoryzacja Protokołu i Uporządkowanie Schematów (`src/protocol/schemas.py`)**:
  - Usunięto nieużywane schematy rejestracji i pomocnicze metody.
  - Wyodrębniono `CloudProviderConfig` z protokołu sieciowego do modułu Kontrolera.
  - Zmieniono nazwę `WSSatelliteEvent` na `WSClientEvent`.
- [x] **Usunięcie Dwuwarstwowej Maszyny Stanów w Satelicie**:
  - Skasowano `SatelliteInteractionState` i plik `states.py`.
  - Przestawiono Satelitę na operowanie wyłącznie w stanach `READY` / `BUSY` ze zdarzeniami emisyjnymi do EventBusa.
- [x] **Audyt i Eliminacja Długu Ewolucyjnego Aplikacji Klienckiej (`src/client`)**:
  - Usunięto przestarzały folder `src/client/legacy/`.
  - Ujednolicono terminologię z `Node` na `Client` w całej konfiguracji i komunikacji z serwerem.
  - Zapewniono płynną migrację kluczy konfiguracyjnych `node_id` -> `client_id`.
- [x] **Spisanie Notatki Projektowej RFC**:
  - Utworzono dokument `docs/context_invalidation_rfc.md` opisujący inwalidację bufora LLM podczas napływu nowych zdarzeń.

---

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-05)

- [x] **Dekompozycja i Przemianowanie Nomenklatury `nodes` -> `clients`**
- [x] **Wprowadzenie Klasy Bazowej Usług (`BaseService`)**
- [x] **Przemianowanie Usługi `llm` na `ollama_worker` oraz Refaktoryzacja `engine.py`**
- [x] **Inicjalizacja Self-Healing i Maszyna Stanów w `ollama_worker`**
- [x] **Protokół Graceful Shutdown i Rozdzielenie Schematów IPC**

---

## Zadania Przyszłe (Nastepny Krok: Refaktoryzacja Kontrolera)

- [ ] **Refaktoryzacja i Oczyszczenie Kontrolera (`src/controller`)**:
  - Przegląd routerów API pod kątem spójności z nowym protokołem WebSocket i rejestrem klientów.
  - Uporządkowanie modułu orkiestracji konwersacji i zdarzeń.
  - Rozważenie implementacji logiki inwalidacji kontekstu z `context_invalidation_rfc.md`.
