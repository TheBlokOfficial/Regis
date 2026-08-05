# HANDOFF: Stan Projektu Regis

## 1. Wykonane Prace w Ostatniej Sesji (2026-08-05)

- **Zmiana Nomenklatury z `nodes` na `clients`**:
  - Całkowicie wyeliminowano starą nomenklaturę `nodes` / `node_id` we wszystkich ścieżkach HTTP i połączeniach WebSocket na rzecz `clients` / `client_id` (np. `/v1/clients/`, `/v1/ws/clients/{client_id}`).
  - Zaktualizowano endpointy routera po stronie Kontrolera (`src/controller/routers/clients.py`) oraz klienta REST we frontendzie (`src/controller/web/api.js`).

- **Zintegrowana Rejestracja w Jednym Kroku (Single-Step WS Registration)**:
  - Usunięto zbędny endpoint rejestracji HTTP REST.
  - Rejestracja klienta odbywa się automatycznie w pierwszej ramce rejestracyjnej wysyłanej przez gniazdo WebSocket tuż po połączeniu. Wyrejestrowanie następuje automatycznie przy `WebSocketDisconnect`.
  - Usunięto przestarzałe wywołanie `fetch_config_and_register()` z punktu wejścia klienta [`src/client/main.py`](file:///d:/Projekty/Regis/src/client/main.py).

- **Wprowadzenie Klasy Bazowej Usług (`BaseService`)**:
  - Utworzono moduł [`src/client/services/base.py`](file:///d:/Projekty/Regis/src/client/services/base.py) udostępniający zunifikowany interfejs dla mikrousług sidecar (`llm`, `audio`, `satellite`).
  - `BaseService` automatyzuje: parsowanie `SERVICE_CONFIG`, utrzymywanie strumienia SSE z magistralą (`/internal/service_commands`), filtrowanie komend po nazwie usługi (`service_name`) oraz przesyłanie wyników zadań (`send_task_event`).
  - Przeprowadzono refaktoryzację orkiestratorów usług: `llm/__main__.py`, `audio/__main__.py` oraz `satellite/__main__.py`, wspinając je na wspólny pniok `BaseService`.
  - Usunięto powielaną logikę odbioru SSE z `src/client/services/satellite/network.py`.

---

## 2. Aktualny Stan Kodu

- **Zarządzanie Usługami (`src/client/services/`)**:
  - `base.py`: Klasa bazowa `BaseService` definiująca cykl życia i komunikację wszystkich bezportowych mikrousług.
  - `llm/`, `audio/`, `satellite/`: Refaktoryzowane, spłaszczone i zunifikowane orkiestratory dziedziczące po `BaseService`.
- **Sieć i Protokół**:
  - WebSocket używa wyłącznie ścieżek `/v1/ws/clients/{client_id}`.
  - `src/client/main.py` inicjalizuje połączenie i rejestrację reaktywnie przez WebSocket.

---

## 3. Kroki Startowe dla Następnego Agenta

1. Obowiązkowo zapoznaj się z [`docs/MANIFEST.md`](file:///d:/Projekty/Regis/docs/MANIFEST.md) oraz [`docs/AGENT_GUIDE.md`](file:///d:/Projekty/Regis/docs/AGENT_GUIDE.md).
2. Sprawdź status aktywnych zadań w [`.agents/TASKS.md`](file:///d:/Projekty/Regis/.agents/TASKS.md).
3. Następnym krokiem w rozwoju projektu mogą być testy integracyjne end-to-end (potok mowy STT -> LLM -> TTS między Satelitą a Kontrolerem).
