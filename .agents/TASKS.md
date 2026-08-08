# Lista Zadań Projektu Regis (TASKS)

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-08 - Unifikacja MessageBus, Katalog Wiadomości i Eliminacja Tight Coupling)

- [x] **Uniwersalna Magistrala Wiadomości (`src/controller/core/message_bus.py`)**:
  - Usunięto rozczłonkowane `command_bus.py` oraz `event_bus.py`. Stworzono lekki (~35 linii) agnostyczny `MessageBus`.
  - Utworzono `telemetry.py` z buforem historii SSE (500 zdarzeń) podłączonym do `message_bus`.
- [x] **Pełny Katalog Silnie Typowanych Wiadomości (`src/controller/messages.py`)**:
  - Stworzono i posegregowano w 4 sekcje klasy wiadomości: `TextMessage`, `AudioMessage` (ze spójnym polem `sender`), `PlayAudioMessage`, `PauseSatelliteMessage`, `ResumeSatelliteMessage`, `ClearHistoryMessage`, `ClientRegisteredMessage`, `ClientUnregisteredMessage`, `ClientUpdatedMessage`, `ClientCommandResultMessage`, `SatelliteEventMessage`, `ConversationTurnMessage`, `SystemLogMessage`.
- [x] **Eliminacja Ciasnych Powiązań (Tight Coupling)**:
  - Usunięto bezpośrednie importy `client_manager` w `interaction.py`, zastępując je publikacją `PlayAudioMessage` i `ResumeSatelliteMessage`.
  - Wdrożono reaktywne słuchacze w `clients.py` sterujące Satelitami przez gniazda WebSocket.
  - Przeniesiono czyszczenie historii w `manager.py` na asynchroniczne wywołania `asyncio.to_thread` reagujące na `ClearHistoryMessage`.
- [x] **Maksymalne Uproszczenie Orkiestratora (`src/controller/orchestrator.py`)**:
  - Usunięto klasę `TurnContext` i funkcję `_build_context`. `handle_text_message` oraz `handle_audio_message` przekazują treść i `sender` bezpośrednio do `_execute_turn_stream`.
  - Odspawano silnik agenta `engine.py` od globalnego `app_state`, wstrzykując `tools_registry` bezpośrednio z Orkiestratora.

---

## Rejestr Zrealizowanych Zadań (Sesja 2026-08-08 - Refaktoryzacja Warstwy Stanu i EventBus SSE)

- [x] **Eliminacja Katalogu `src/controller/core/state/`**:
  - Usunięto cały folder `state/` usuwając zbędny bloatware.
- [x] **Dostawcy Chmury w Config i Endpoints (`endpoints/cloud.py`)**:
  - Przeniesiono `cloud_store.py` do `endpoints/cloud.py` używając schematu `CloudProvidersConfig` i `config.load()` / `config.save()`.
- [x] **Zarządzanie Klientami (`endpoints/clients.py` & `core/client_registry.py`)**:
  - Zmigrowano obsługę połączeń WS, rejestrację i zapis konfiguracji `ClientsConfig` do `endpoints/clients.py`.
  - Stworzono lekki rejestr w pamięci RAM `core/client_registry.py`.
- [x] **Wyniesienie EventBus i SSE (`core/event_bus.py` & `/api/events`)**:
  - Przeniesiono `event_bus.py` do `core/event_bus.py`.
  - Dodano endpoint SSE `/api/events` w `endpoints/system.py`.
- [x] **Przeniesienie Stanu Runtime (`core/state.py`)**:
  - Przeniesiono zmienne stanu runtime z `app_state.py` do `core/state.py`.
- [x] **Aktualizacja Importów i Testów**:
  - Zaktualizowano wszystkie ścieżki w kodzie oraz poprawiono zestaw testów w `tests/test_llm_backends.py`.

---

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

## Zadania Przyszłe

- [ ] **Wdrożenie Podmiotu `AgentGateway`**:
  - Stworzenie `src/controller/core/agent_gateway.py` nasłuchującego wiadomości przeznaczonych dla Agenta i generującego zunifikowany `InputContext` dla Orkiestratora.
- [ ] **FastAPI Dependency Injection**:
  - `state.py` jako moduł z globalnymi zmiennymi jest krokiem przejściowym. Docelowo `AppState` przez `Depends()` w routerach.
- [ ] **Wdrożenie Dwuwarstwowych Sub-Agentów**:
  - Implementacja wzorca Mixture of Specialist Sub-Agents opisanego w `docs/hierarchical_subagents_rfc.md`.
- [ ] **Pamięć Długoterminowa** `[ARCH]`:
  - Kluczowy brakujący feature odróżniający Regisa od HA AI. Nowe rozwiązanie wymaga osobnej sesji architektonicznej.
- [ ] **Scheduler Zadań Agenta** `[ARCH]`:
  - Mechanizm odroczonych "szturchnięć" agenta. Niezaprojektowany, wymaga sesji architektonicznej.
- [ ] **Docker Deployment** `[DIST]`:
  - Cel dystrybucyjny: Regis jako obraz Docker na mini PC.
