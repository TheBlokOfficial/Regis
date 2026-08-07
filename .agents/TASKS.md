# Lista Zadań Projektu Regis (TASKS)

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-07 - Refaktoryzacja Kontrolera)

- [x] **Centralizacja Persystencji (`JSONStorage`)**:
  - Utworzono wątkowo bezpieczny pomocnik `JSONStorage` z per-plikowymi blokadami oraz atomowym zapisem (`os.replace`).
- [x] **Podział Kontrolera na 6 Domen**:
  - Reorganizacja kodu w `src/controller` na 6 spójnych katalogów: `config/`, `core/`, `llm/`, `integrations/`, `tools/`, `api/`.
- [x] **Silne Typowanie Pydantic (`BaseConfigModel`)**:
  - Wdrożono klasę bazową `BaseConfigModel` wymuszającą obecność wewnętrznej klasy `Meta` z `file_name`.
  - Stworzono schematy Pydantic: `SystemSettings`, `RoomsConfig`, `AliasesConfig`, `VirtualGroupsConfig`.
  - Wprowadzono jednolite API: `config.load(SchemaClass)` i `config.save(instance)`.
- [x] **Hermetyzacja i Czyszczenie Cyklu Życia (`app.py`)**:
  - Uproszczono funkcję `lifespan` w `app.py` do czytelnych 3 kroków.
  - Wyeliminowano sztuczny import `tools_config` oraz ręczne rozgrzebywanie słowników.
- [x] **Ujednoznacznienie Nomenklatury Rejestrów**:
  - Zmieniono nazwy: `core/registry.py` $\rightarrow$ `client_registry.py`, `tools/registry.py` $\rightarrow$ `tools_registry.py`.
  - Usunięto nie-typowany plik `src/controller/tools/config.py`.
- [x] **Dokumentacja Architektoniczna (RFC)**:
  - Utworzono dokument [`docs/hierarchical_subagents_rfc.md`](file:///d:/Projekty/Regis/docs/hierarchical_subagents_rfc.md) dotyczący dwuwarstwowych sub-agentów.

---

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-07 - Protokół i Klient)

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

---

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-07 - Refaktoryzacja Rdzenia Kontrolera)

- [x] **Rozbicie `core/client_registry.py`**:
  - Zastąpiono globalny moduł-worek czterema dedykowanymi plikami: `app_state.py`, `connection_manager.py`, `client_store.py`, `session_store.py`, `heartbeat.py`.
  - Clean break — 9 importerów zaktualizowanych, stary plik usunięty.
- [x] **Optymalizacja i Dekompozycja Orkiestratora (`src/controller/llm/orchestrator.py`)**:
  - Monolityczna `proxy_sse_to_queue()` (442 linie) rozbita na `llm/pipeline/cloud.py`, `llm/pipeline/worker.py`, `llm/pipeline/session_manager.py`.
  - Orkiestrator zredukowany do ~70-linijnej fasady routingowej.
  - Naprawiono broken ścieżkę worker (mechanizm `_pending_tasks` zamiast `event_bus.subscribe(callback)`).
- [x] **Granica `tools/` ↔ `llm/prompt/`**:
  - Utworzono `tools/schemas.py` jako single point of definition dla `BASE_TOOLS_SCHEMA`.
- [x] **4 poprawki błędów krytycznych**:
  - `save_cloud_providers` cache, `OllamaBackend model_name`, `/v1/rooms`, `task_event routing`.

---

## Zadania Przyszłe

- [ ] **Uproszczenie `llm/backends/`**:
  - `ollama.py` i `openrouter.py` mają własne pętle ReAct (140-200 linii). Po przeniesieniu logiki ReAct do `pipeline/worker.py` backendy mogą stać się czystymi wrapperami HTTP.
- [ ] **FastAPI Dependency Injection**:
  - `app_state.py` jako moduł z globalnymi zmiennymi jest krokiem przejściowym. Docelowo `AppState` przez `Depends()` w routerach.
- [ ] **Wdrożenie Dwuwarstwowych Sub-Agentów**:
  - Implementacja wzorca Mixture of Specialist Sub-Agents opisanego w `docs/hierarchical_subagents_rfc.md`.
