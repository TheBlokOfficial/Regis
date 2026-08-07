# HANDOFF — Stan Projektu Regis po Sesji 2026-08-07

## Co zostało zrobione w tej sesji

### Pełna refaktoryzacja rdzenia kontrolera (`src/controller/`)

Przeprowadzono kompleksową refaktoryzację modułu `controller` w dwóch głównych obszarach:

#### 1. Rozbicie `core/client_registry.py` (globalny worek → 4 dedykowane moduły)

Stary plik `client_registry.py` miał 7 odpowiedzialności i był importowany przez 9 plików jako globalny singleton. Zastąpiono go przez:

- **`core/app_state.py`** — centralny rejestr zmiennych stanu runtime (`ha_client`, `tools_registry`, `integration_registry`, `_settings_cache`, `controller_start_time`)
- **`core/connection_manager.py`** — klasa `ClientConnectionManager` + instancja `client_manager` (WebSocket transport)
- **`core/client_store.py`** — rejestr aktywnych klientów, persystencja (`clients.json`), kwerendy po typie usługi (`get_llm_clients`, `get_audio_clients`, `get_satellite_clients`)
- **`core/session_store.py`** — historia konwersacji per sesja/satelita (`conversation_sessions`, `session_last_interaction_times`, `get/append/clear_session_history`)
- **`core/heartbeat.py`** — wydzielona pętla heartbeat czyszcząca nieaktywne sesje i martwe połączenia

Stary `client_registry.py` usunięty. Clean break — wszystkich 9 importerów zaktualizowanych.

#### 2. Rozbicie `llm/orchestrator.py` (442 linie → ~70 linii fasady)

Monolityczna `proxy_sse_to_queue()` zastąpiona przez warstwową architekturę pipeline:

- **`llm/pipeline/session_manager.py`** — `save_and_publish(satellite_id, turn)` eliminuje duplikację logiki zapisu historii i EventBus (była powtórzona dwa razy)
- **`llm/pipeline/cloud.py`** — ścieżka OpenRouter (bezpośrednie wywołanie backendu na Kontrolerze)
- **`llm/pipeline/worker.py`** — ścieżka STT→LLM→TTS z mechanizmem `_pending_tasks` (słownik `task_id → asyncio.Queue`), który zastąpił broken `event_bus.subscribe(callback)` — ścieżka worker była całkowicie niefunkcjonalna
- **`llm/orchestrator.py`** — cienka fasada (~70 linii): wybiera cloud vs. worker i deleguje

#### 3. Granica `tools/` ↔ `llm/prompt/`

- Utworzono **`tools/schemas.py`** jako single point of definition dla `BASE_TOOLS_SCHEMA`
- `llm/prompt/tools_schema.py` stał się re-eksportem z `tools/schemas.py`
- Odwrócona zależność (tools → llm) została naprawiona

#### 4. Poprawki 4 błędów krytycznych

- `save_cloud_providers()` — cache nie był odświeżany po zapisie (naprawiono bezwarunkowym `reload_cloud_providers()`)
- `OllamaBackend(model_name="worker")` — hardkodowana nazwa zamiast `worker.get("model_name")`
- `/v1/rooms` — `config.load_rooms()` nie istniało (naprawiono na `config.load(RoomsConfig).root`)
- `task_event` w `api/clients.py` — ślepa publikacja do EventBus zastąpiona `worker.route_task_event(task_id, event)`

### Wynik weryfikacji

```
python -c "import controller.app; print('OK')"
→ OK (exit code 0)
```

Brak referencji do `core.client_registry` w żadnym pliku kontrolera.

---

## Aktualny stan kodu

Architektura `src/controller/core/` jest teraz spójna ze strukturą modułu `src/client/` (czytelne warstwy, jedno zadanie per plik). Orkiestrator jest cienką fasadą. Zależności między modułami są jednokierunkowe.

### Pliki które NIE były ruszane w tej sesji

- `llm/backends/` — `ollama.py`, `openrouter.py` (zawierają własne pętle ReAct — dalszy potencjalny refaktoring)
- `integrations/` — bez zmian
- `config/` — bez zmian
- `llm/session/history.py`, `llm/models.py` — bez zmian
- Moduły `src/client/`, `src/protocol/` — bez zmian

---

## Precyzyjne kroki startowe dla następnego agenta

1. Wczytaj `docs/MANIFEST.md` i `docs/AGENT_GUIDE.md` zgodnie z procedurą startową.
2. Uruchom smoke test: `cd src && python -c "import controller.app; print('OK')"` — powinien przejść.
3. Jeśli użytkownik chce kontynuować refaktoryzację, kolejne obszary to:
   - **`llm/backends/`** — `ollama.py` i `openrouter.py` mają własne pętle ReAct (140-200 linii każdy). Po refaktoryzacji `worker.py` przejął logikę pętli, więc backendy mogą zostać uproszczone do czystych wrapperów HTTP.
   - **FastAPI Dependency Injection** — `app_state.py` jako moduł z zmiennymi globalnymi jest krokiem przejściowym. Docelowo DI przez `Depends()` w routerach.
4. Stary plik `core/client_registry.py` nie istnieje — nie próbuj go przywrócić.

---

## Zadania TASKS.md

Zadanie "Optymalizacja i Dekompozycja Orkiestratora" zostało zrealizowane w tej sesji (oznaczone jako [x]).
