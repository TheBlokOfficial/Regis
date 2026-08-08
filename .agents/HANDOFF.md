# HANDOFF — Stan Projektu Regis po Sesji 2026-08-08

## Co zostało zrobione w tej sesji

Przeprowadzono pełną restrukturyzację architektoniczną Kontrolera (`src/controller`), uzgadniając kod z trójwarstwowym modelem z `docs/MANIFEST.md` oraz eliminując dług ewolucyjny wokół `llm/`, `tools/`, `audio/` i `api/`.

### 1. Wydzielenie czystego Mózgu Agenta ReAct (`src/controller/agent/`)
- Stworzono dedykowany moduł agentyczny: `engine.py` (ReAct loop i wykonawca narzędzi), `prompt/` (`builder.py`, `tools_schema.py`), `models.py` (`SUPPORTED_REGIS_MODELS`).
- Pętla agenta w `agent/engine.py` opiera się teraz na zunifikowanym dynamicznym rozwiązaniu dostawców (`providers/llm/resolver.py`).
- Wyeliminowano starą zniekształconą strukturę `src/controller/llm/`.

### 2. Hermetyzacja Rąk Agenta (`src/controller/agent/tools/`)
- Przemieszczono rejestr narzędzi oraz ich schematy JSON ze starego katalogu nadrzędnego `tools/` do wewnętrznego modułu Agenta `src/controller/agent/tools/` (`registry.py`, `schemas.py`).
- Usunięto top-level katalog `src/controller/tools/`.

### 3. Zjednoczenie Dostawców Zmysłów w Warstwie 2 (`src/controller/providers/`)
- Utworzono podkatalog `providers/llm/` mieszczący wszystkie konkretne dostawcy LLM: `openrouter.py`, `ollama.py`, `client_app.py`, `base.py`, `resolver.py`.
- Utworzono `providers/audio/service.py`, wyciągając niskopoziomową komunikację HTTP z serwisami STT i TTS (Whisper, Piper) z Orkiestratora.
- Usunięto katalogi `src/controller/audio/` oraz `src/controller/llm/`.

### 4. Konsolidacja Pamięci Sesji w Warstwie 1 Core (`src/controller/core/session/`)
- Przeniesiono odpowiedzialność zarządzania historią rozmów oraz sesją do `src/controller/core/session/`:
  - `store.py` — rejestr sesji w pamięci i timery
  - `history.py` — budowanie listy wiadomości LLM z wpisów czatu i narzędzi
  - `manager.py` — zapisywanie tur, publikowanie zdarzeń czatu i czyszczenie historii.
- Usunięto stare pliki `src/controller/core/session_store.py` oraz metody czyszczenia z Orkiestratora.

### 5. Przemieszczenie Orkiestratora do Warstwy 1 Core (`src/controller/core/orchestrator.py`)
- Przeniesiono `orchestrator.py` z `llm/` do `src/controller/core/orchestrator.py`.
- Przekształcono go w czystą, wysokopoziomową fasadę tury konwersacyjnej (`execute_interaction_turn`), łączącą STT -> Agent Engine -> TTS.

### 6. Przemianowanie i Uporządkowanie Endpointów HTTP/WS (`src/controller/endpoints/`)
- Zastąpiono dawny katalog `src/controller/api/` zrefaktoryzowanym modułem **`src/controller/endpoints/`**:
  - `interaction.py` — tury czatu tekstowego i nagrań audio (`/v1/chat/*`)
  - `clients.py` — obsługa rejestracji, konfiguracji oraz głównego tunelu WebSocket (`/v1/clients/*`, `/v1/ws/clients/*`)
  - `cloud.py` — zarządzanie kluczami dostawców chmurowych (`/api/cloud-providers`)
  - `system.py` — strumieniowanie SSE i snapshot stanu (`/api/events`, `/api/status`)
  - `tools.py` — proxy wywołań narzędzi (`/v1/tools/*`)
- Usunięto martwe i przestarzałe trasy:
  - Skasowano nieużywany HTTP POST `/api/satellite/event`.
  - Przeniesiono i zrefaktoryzowano komendy klientów z `/api/node/{node_id}/command` do `POST /v1/clients/{client_id}/command` (z zachowaniem aliasu).
  - Wymieniono potężny monolityczny `if-elif` w połączeniu WebSocket na przejrzystą mapę handlerów zdarzeń (`WS_EVENT_HANDLERS`).

---

## Aktualny stan kodu

- Kod jest w pełni sprawny i zrefaktoryzowany zgodnie z 3-warstwowym modelem architektonicznym.
- **Weryfikacja testami:** `pytest tests/test_llm_backends.py` (10/10 testów przechodzi, 100% PASSED).
- Nowy układ katalogów Kontrolera (`src/controller/`):
  - `core/` (Układ nerwowy, orchestrator, session/, client_store, app_state)
  - `agent/` (Mózg agenta ReAct, engine, prompt/, tools/, models)
  - `providers/` (Backendy zmysłów llm/ oraz audio/service.py)
  - `endpoints/` (Punkty HTTP/WS interaction, clients, cloud, system, tools)
  - `config/`, `integrations/`, `web/`

---

## Otwarte kwestie do przyszłych sesji

1. **Pamięć długoterminowa** `[ARCH]` — kluczowy brakujący feature odróżniający Regisa od HA AI.
2. **Scheduler zadań agenta** `[ARCH]` — mechanizm odroczonych szturchnięć agenta.
3. **Docker deployment** `[DIST]` — przygotowanie obrazów Docker dla serwera Regis.
4. **FastAPI Dependency Injection** — usunięcie globali `app_state` na rzecz `Depends()`.

---

## Precyzyjne kroki startowe dla następnego agenta

1. Wczytaj `docs/MANIFEST.md` oraz `.agents/AGENTS.md`.
2. Przeprowadź smoke test: `pytest tests/test_llm_backends.py` z poziomu głównego katalogu.
3. Zapoznaj się z nową strukturą w `src/controller/`: `core/`, `agent/`, `providers/`, `endpoints/`.
