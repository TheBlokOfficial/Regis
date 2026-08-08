# HANDOFF — Stan Projektu Regis po Sesji 2026-08-08 (Unifikacja MessageBus, Katalog Wiadomości i Eliminacja Tight Coupling)

## Co zostało zrobione w tej sesji

Przeprowadzono pełną restrukturyzację szyny wiadomości, stworzono silnie typowany katalog wiadomości w `src/controller/messages.py` oraz wyeliminowano ciasne powiązania (tight coupling) w całym Kontrolerze na rzecz czystej architektury sterowanej zdarzeniami (Event-Driven Architecture).

### 1. Uniwersalna Magistrala Wiadomości (`core/message_bus.py`)
- Usunięto przestarzałe, rozczłonkowane pliki `command_bus.py` oraz `event_bus.py`.
- Stworzono agnostyczny, lekki (~35 linii) moduł [src/controller/core/message_bus.py](file:///d:/Projekty/Regis/src/controller/core/message_bus.py) udostępniający wyłącznie metody `subscribe` oraz `publish`.

### 2. Pełny Katalog Silnie Typowanych Wiadomości (`messages.py`)
- Utworzono i zorganizowano w 4 tematyczne sekcje plik [src/controller/messages.py](file:///d:/Projekty/Regis/src/controller/messages.py):
  1. **Intencje Wejściowe Użytkownika:** `TextMessage`, `AudioMessage` (ze spójnym polem `sender: str = "web_ui"`).
  2. **Komendy Sterujące i Akcje:** `PlayAudioMessage`, `PauseSatelliteMessage`, `ResumeSatelliteMessage`, `ClearHistoryMessage`.
  3. **Zdarzenia Sieciowe i Cykl Życia Klientów:** `ClientRegisteredMessage`, `ClientUnregisteredMessage`, `ClientUpdatedMessage`, `ClientCommandResultMessage`, `SatelliteEventMessage`.
  4. **Telemetria i Logs:** `ConversationTurnMessage`, `SystemLogMessage`.

### 3. Usunięcie Tight Coupling i Reaktywne WS
- Odpięto router [src/controller/endpoints/interaction.py](file:///d:/Projekty/Regis/src/controller/endpoints/interaction.py) od bezpośrednich wywołań menedżera gniazd WebSocket (`client_manager`). Endpointy wypluwają teraz paczki `PlayAudioMessage`, `ResumeSatelliteMessage` oraz `ClearHistoryMessage` na `message_bus`.
- Zarejestrowano w [src/controller/endpoints/clients.py](file:///d:/Projekty/Regis/src/controller/endpoints/clients.py) słuchacze komend sterujących, które asynchronicznie wysyłają polecenia do Satelit po WebSocket.
- Odblokowano pętlę asynchroniczną podczas czyszczenia historii w [src/controller/agent/session/manager.py](file:///d:/Projekty/Regis/src/controller/agent/session/manager.py) (`asyncio.to_thread` przy `requests.post`).

### 4. Uproszczenie Orkiestratora i Dependency Injection dla Agenta
- Zrefaktoryzowano [src/controller/orchestrator.py](file:///d:/Projekty/Regis/src/controller/orchestrator.py): usunięto sztuczną klasę `TurnContext` i funkcję pomocniczą `_build_context`. `handle_text_message` i `handle_audio_message` przekazują treść i `sender` bezpośrednio do `_execute_turn_stream`.
- Usunięto sztywny import `app_state` z [src/controller/agent/engine.py](file:///d:/Projekty/Regis/src/controller/agent/engine.py), wstrzykując `tools_registry` bezpośrednio z Orkiestratora.

### 5. Zaplanowanie Bramy Agenta (`AgentGateway`)
- Uzgodniono wprowadzenie aktywnego podmiotu `AgentGateway` (`agent_gateway.py`), którego zadaniem będzie nasłuchiwanie na `message_bus` wszelkich zapytań skierowanych do Agenta (z HTTP, WS, konsoli), rozpakowanie kontekstu nadawcy oraz zunifikowanie ich w paczkę `InputContext`.

---

## Aktualny stan kodu

- Kod w pełni sprawny, architektura wyczyszczona i zunifikowana wokół `message_bus`.
- **Weryfikacja testami:** `python -c "from controller.app import app" ; pytest tests/test_llm_backends.py` (10/10 testów przechodzi, 100% PASSED).
- Układ katalogów Kontrolera (`src/controller/`):
  - `core/` (`message_bus.py`, `telemetry.py`, `client_registry.py`, `state.py`, `session/`)
  - `agent/` (`engine.py`, `prompt/`, `tools/`, `models.py`)
  - `providers/` (`llm/`, `audio/service.py`)
  - `endpoints/` (`interaction.py`, `clients.py`, `cloud.py`, `system.py`, `tools.py`)
  - `messages.py`, `orchestrator.py`, `config/`, `integrations/`, `web/`

---

## Otwarte kwestie do przyszłych sesji

1. **Wdrożenie Podmiotu `AgentGateway`** — stworzenie `src/controller/core/agent_gateway.py` nasłuchującego wiadomości dla Agenta i generującego `InputContext` dla Orkiestratora.
2. **Pamięć długoterminowa** `[ARCH]` — kluczowy brakujący feature odróżniający Regisa od HA AI.
3. **Scheduler zadań agenta** `[ARCH]` — mechanizm odroczonych szturchnięć agenta.
4. **Docker deployment** `[DIST]` — przygotowanie obrazów Docker dla serwera Regis.

---

## Precyzyjne kroki startowe dla następnego agenta

1. Zapoznaj się z `docs/MANIFEST.md` oraz `.agents/AGENTS.md`.
2. Uruchom test weryfikacyjny: `python -c "from controller.app import app" ; pytest tests/test_llm_backends.py` w głównym katalogu.
3. Przejrzyj spójny katalog wiadomości w [src/controller/messages.py](file:///d:/Projekty/Regis/src/controller/messages.py) oraz zrefaktoryzowany [src/controller/orchestrator.py](file:///d:/Projekty/Regis/src/controller/orchestrator.py).
4. Zapoznaj się z zaakceptowanym planem w `implementation_plan.md` dotyczącym wprowadzenia `AgentGateway`.
