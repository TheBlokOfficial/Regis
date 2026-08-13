# Manifest Architektoniczny Systemu Regis

## 1. Wizja i Cel Systemu Regis

**System Regis** to modularna platforma usług rozproszonych komunikujących się w sieci lokalnej, przeznaczona do orkiestracji i wykonywania zadań przez inteligentnych agentów AI.

Kluczowe założenia architektoniczne Systemu Regis:
- **Lokalność i Rozproszenie**: Usługi działają wydajnie w sieci lokalnej z pełną kontrolą nad prywatnością danych i przepływem informacji.
- **Hybrydowość modeli LLM**: Przezroczysta obsługa lokalnych modeli językowych (np. Ollama) oraz modeli chmurowych (np. OpenRouter).
- **Czas Rzeczywisty**: Dwukierunkowa, strumieniowa komunikacja oparta o WebSockets oraz asynchroniczną magistralę zdarzeń (`EventBus`).
- **Niezawodność i Kontrola**: Wbudowany mechanizm kontroli zadań, natychmiastowe anulowanie generowania odpowiedzi oraz izolacja sesji użytkowników.

---

## 2. Struktura Monorepo i Zależności Workspace

Projekt wykorzystuje architekturę monorepo zarządaną przez menedżera `uv` (`uv workspace`):

```text
Regis/
├── docs/             # Dokumentacja architektoniczna i wdrożeniowa
│   ├── manifest.md   # Manifest Architektoniczny Systemu Regis
│   └── onboarding.md # Jednolity przewodnik deweloperski
├── packages/         # Wspólne pakiety kodowe
│   └── shared/       # Paczka shared (ConfigStore, EventBus, DTO, logging)
├── services/         # Niezależne usługi sieciowe
│   └── server/       # Główna usługa serwera Regis (bramka REST/WS, engine, rejestr backendów)
├── pyproject.toml    # Główna konfiguracja workspace oraz pytest
└── README.md         # Wprowadzenie do projektu
```

### Relacje przestrzeni roboczej:
- **`packages/shared`** pełni rolę rdzenia infrastrukturalnego – nie posiada zależności od konkretnych usług i definiuje kontrakty danych (DTO), rejestr zdarzeń i logowanie.
- **`services/server`** (oraz przyszłe usługi w `services/*`) importują `shared` jako zależność workspace (`shared = { workspace = true }`).

---

## 3. Szczegółowy Opis Warstw Architektury

```text
+-----------------------------------------------------------------------+
|                         WARSTWA INTERFEJSU (SPA)                      |
|                  services/server/src/server/web (HTML/JS/CSS)        |
+-----------------------------------------------------------------------+
                                   | REST / WebSockets Streaming
                                   v
+-----------------------------------------------------------------------+
|                         WARSTWA SIECIOWA (GATEWAY)                    |
|                services/server/src/server/network (FastAPI)           |
+-----------------------------------------------------------------------+
                     |                                    |
                     v                                    v
+------------------------------------------+  +-------------------------+
|        WARSTWA RDZENIA AGENTA            |  |  WARSTWA WSPÓŁNA        |
|  services/server/src/server/agent        |  |  packages/shared        |
|  - AgentEngine                           |  |  - EventBus             |
|  - MemoryManager (Session storage)       |  |  - ConfigStore          |
|  - ContextBuilder                        |  |  - Contracts (DTOs)     |
+------------------------------------------+  |  - Logging              |
                     |                        +-------------------------+
                     v                                    ^
+------------------------------------------+              |
|        WARSTWA DOSTAWCÓW LLM             |              |
|  services/server/src/server/agent/backend|--------------+
|  - BackendRegistry                       |
|  - BaseLLMProvider (Ollama, OpenRouter)  |
+------------------------------------------+
```

### 3.1 Warstwa Sieciowa (`services/server/src/server/network`)
- **FastAPI Gateway (`gateway.py`) i zmodularyzowane routery (`routes/`)**: Obsługują punkty końcowe REST i SSE API v1 z podziałem na dedykowane pod-routery:
  - **`routes/health.py`**: Status zdrowia bramki i modułów (`GET /api/v1/health`).
  - **`routes/providers.py`**: Konfiguracja i zarządzenie dostawcami LLM (`GET/POST/PUT/DELETE /api/v1/llm/providers/*`, schemas).
  - **`routes/chat.py`**: Interakcje synchroniczne, strumieniowanie SSE i anulowanie (`POST /api/v1/chat/*`).
  - **`routes/sessions.py`**: Zarządzanie i historia sesji konwersacji (`GET/POST/DELETE /api/v1/chat/sessions/*`).
- **Gateway (`gateway.py`)**: Serwuje wbudowaną konsolę WWW (SPA) oraz rejestruje centralny router API v1 (`create_api_router`). W modelu pojedynczej usługi strumieniowanie tokenów do konsoli realizowane jest przez protokół **SSE**. Dwukierunkowa bramka **WebSockets** (`ws://127.0.0.1:8000/ws`) jest zaplanowana jako punkt komunikacji w architekturze rozproszonej z wieloma usługami satelitarnymi.

### 3.2 Warstwa Rdzenia Agenta (`services/server/src/server/agent`)
- **`AgentEngine` (`engine.py`)**: Serce orkiestracji Systemu Regis. Kontroluje aktywne zadania konwersacyjne (`_active_tasks`), zarządza cyklem życia sesji oraz udostępnia metody `interact_stream` i `cancel_interaction`.
- **`MemoryManager` (`memory/session.py`)**: Odpowiada za utrwalanie historii rozmów per sesja na dysku (`data/sessions/*.json`).
- **`ContextBuilder` (`context/builder.py`)**: Komponuje ostateczny prompt dla LLM, łącząc instrukcje systemowe z historią sesji. Przycina historię do `max_history_messages` najnowszych wiadomości (domyślnie 40, konfigurowalne w `settings.json`), by uniknąć przekroczenia limitu kontekstu modelu w długich konwersacjach. Przycinanie działa na podstawie liczby wiadomości, nie realnego zliczania tokenów.
- **`Tools` (`tools/`)**: Moduł rozszerzeń dedykowany dla automatycznego wywoływania funkcji (Tool Calling) przez agentów *(w fazie planowania architektonicznego)*.

### 3.3 Warstwa Dostawców LLM (`services/server/src/server/agent/backend`)
- **`BaseLLMProvider` (`providers/base.py`)**: Interfejs abstrakcyjny definiujący spójną metodę strumieniowania `generate_stream(messages)`.
- **`BackendRegistry` (`registry.py`)**: Dynamiczny rejestr dostawców modeli z możliwością płynnego przełączania aktywnego backendu (np. z lokalnego `OllamaProvider` na chmurowy `OpenRouterProvider`).

### 3.4 Warstwa Wspólna (`packages/shared/src/shared`)
- **`ConfigStore` (`config.py`)**: Centralny zarządca persystentnej konfiguracji w formacie JSON z automatyczną walidacją i domyślnymi wartościami.
- **`EventBus` (`event_bus.py`)**: Asynchroniczna magistrala zdarzeń pub/sub (`subscribe`/`publish`), w pełni zaimplementowana w `packages/shared`. **Uwaga**: instancja `EventBus` jest tworzona w `main.py` i przekazywana do `create_gateway_app`, ale obecnie nie jest jeszcze podłączona do `AgentEngine` ani używana do publikowania jakichkolwiek zdarzeń — `events.py` (`ServerEventType`) jest na razie pustym enumem. Realne wpięcie do przepływu strumieniowania to niezaimplementowany punkt rozwoju (patrz sekcja 5).
- **`contracts.py`**: Definicje obiektów transferu danych (DTO), m.in. `ChatMessageDTO`, `ChatResponseDTO`, `SendChatMessageRequest` oraz struktury odpowiedzi API.
- **`logging.py`**: Jednolita konfiguracja logów dla całego monorepo z ustandaryzowanymi nazwami kategorii (`regis.main`, `regis.agent`, itp.).

---

## 4. Przepływy Danych (Sequence Flow)

### 4.1 Przepływ Strumieniowej Interakcji (SSE - Server-Sent Events)
```text
Klient (Web UI)        FastAPI Gateway          AgentEngine        MemoryManager        LLM Provider        EventBus
       |                       |                     |                   |                   |                 |
       |-- POST /chat/stream ->|                     |                   |                   |                 |
       |                       |--- interact_stream ->|                   |                   |                 |
       |                       |                     |--- add_message -->|                   |                 |
       |                       |                     |--- build_messages ------------------->|                 |
       |                       |                     |--- generate_stream ------------------>|                 |
       |<-- sse data chunk ----|<-- yield chunk -----|                   |                   |                 |
       |<-- sse data chunk ----|<-- yield chunk -----|                   |                   |                 |
       |                       |                     |--- add_assistant_msg -->|                |                 |
       |                       |                     |--- publish_event [PLANOWANE, niepodłączone] ------------>|
       |<-- sse data [DONE] ---|                     |                   |                   |                 |
```
> **Status implementacji**: krok `publish_event` jest częścią docelowego projektu przepływu, ale obecnie nie istnieje w kodzie — `AgentEngine` nie wywołuje `EventBus.publish()`. Zobacz uwagę w sekcji 3.4.

### 4.2 Przepływ Przerwania / Anulowania Zapytania
```text
Klient (Web UI)        REST Gateway            AgentEngine         Task (Asyncio)       MemoryManager
       |                    |                       |                    |                    |
       |-- POST /cancel --->|                       |                    |                    |
       |                    |-- cancel_interaction ->|                   |                    |
       |                    |                       |-- task.cancel() -->|                    |
       |                    |                       |                    |-- CancelledError ->|
       |                    |                       |                    |-- add "[Przerwano]"|
       |<-- 200 OK ---------|<-- status: cancelled -|                    |                    |
```

---

## 5. Standardy i Kierunki Rozwoju

1. **SOLID, DRY, KISS**: Kod projektowany jest w sposób modułowy, ze ścisłym rozdzieleniem odpowiedzialności.
2. **Rozbudowa Narzędzi (Tool Calling)**: Moduł `server.agent.tools` stanowi planowany punkt rozszerzeń dla automatycznego wywoływania funkcji zewnętrznych przez agentów.
3. **Pamięć Długoterminowa i Wektorowa**: Planowana integracja modułów pamięci wektorowej i semantycznej w usłudze `server`.
4. **Skalowanie Usług Rozproszonych & WebSockets**: Przygotowanie infrastruktury `services/` pod uruchamianie dedykowanych mikrousług specjalistycznych w sieci lokalnej i ich komunikacji via WebSockets.
