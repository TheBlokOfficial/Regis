# Lista Zadań Projektu Regis (TASKS)

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-08 - Restrukturyzacja Architektoniczna Kontrolera)

- [x] **Rozdzielenie Orkiestratora i Konsolidacja Pamięci Sesji**:
  - Przeniesiono zarządcę sesji i czyszczenie historii do `src/controller/core/session/` (`store.py`, `history.py`, `manager.py`).
  - Usunięto stary plik `session_store.py`.
- [x] **Wydzielenie Czystego Mózgu Agenta ReAct (`src/controller/agent/`)**:
  - Utworzono pętlę agenta ReAct w `agent/engine.py`.
  - Przeniesiono prompt systemowy do `agent/prompt/` oraz definicje modeli do `agent/models.py`.
- [x] **Hermetyzacja Rąk Agenta (`src/controller/agent/tools/`)**:
  - Przeniesiono `tools_registry.py` oraz `schemas.py` z top-level `tools/` do `agent/tools/`.
  - Usunięto stary katalog `src/controller/tools/`.
- [x] **Ujednolicenie Dostawców Zmysłów w Warstwie 2 (`src/controller/providers/`)**:
  - Skonsolidowano dostawców LLM pod `providers/llm/` (`openrouter.py`, `ollama.py`, `client_app.py`, `base.py`, `resolver.py`).
  - Utworzono `providers/audio/service.py` realizujący niskopoziomowe zapytania HTTP do STT/TTS.
  - Usunięto katalogi `src/controller/llm/` oraz `src/controller/audio/`.
- [x] **Przemianowanie i Uporządkowanie Endpointów (`src/controller/endpoints/`)**:
  - Przeniesiono dawne `api/` do `src/controller/endpoints/` (`interaction.py`, `clients.py`, `cloud.py`, `system.py`, `tools.py`).
  - Usunięto martwy endpoint `POST /api/satellite/event`.
  - Przeniesiono i zrefaktoryzowano komendy do klienta na `POST /v1/clients/{client_id}/command`.
  - Zrefaktoryzowano pętlę WebSocket w `clients.py` na słownikową mapę handlerów zdarzeń.

---

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

## Zadania Przyszłe

- [ ] **FastAPI Dependency Injection**:
  - `app_state.py` jako moduł z globalnymi zmiennymi jest krokiem przejściowym. Docelowo `AppState` przez `Depends()` w routerach.
- [ ] **Wdrożenie Dwuwarstwowych Sub-Agentów**:
  - Implementacja wzorca Mixture of Specialist Sub-Agents opisanego w `docs/hierarchical_subagents_rfc.md`.
- [ ] **Pamięć Długoterminowa** `[ARCH]`:
  - Kluczowy brakujący feature odróżniający Regisa od HA AI. Stary system Notatnika wycięty. Nowe rozwiązanie (wektorowe lub inne) wymaga osobnej sesji architektonicznej.
- [ ] **Scheduler Zadań Agenta** `[ARCH]`:
  - Mechanizm odroczonych "szturchnięć" agenta (np. "sprawdź za godzinę czy nikogo nie ma w domu"). Niezaprojektowany, wymaga sesji architektonicznej.
- [ ] **Docker Deployment** `[DIST]`:
  - Cel dystrybucyjny: Regis jako obraz Docker na mini PC, analogia do instalacji HA. Ustalony jako docelowy model dystrybucji w sesji 2026-08-07. Niezaimplementowany.
- [ ] **Formalne Interfejsy Warstwy 2** `[ARCH]`:
  - `ILLMProvider`, `ISTTProvider`, `ITTSProvider`, `ISatellite` istnieją jako koncepcja w MANIFEST §3.1 — nie są jeszcze sformalizowane jako klasy bazowe w kodzie.
