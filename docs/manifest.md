# Manifest Architektoniczny Systemu Regis

## 1. Wizja i Cel Systemu Regis

**System Regis** to modularna platforma usług rozproszonych komunikujących się w sieci lokalnej, przeznaczona do orkiestracji i wykonywania zadań przez inteligentnych agentów AI.

Kluczowe założenia architektoniczne Systemu Regis:
- **Lokalność i Rozproszenie**: Usługi działają wydajnie w sieci lokalnej z pełną kontrolą nad prywatnością danych i przepływem informacji. *(Dziś: jedna usługa `services/server`; wielousługowość to kierunek, nie stan obecny — patrz sekcja 5.)*
- **Hybrydowość modeli LLM**: Przezroczysta obsługa lokalnych modeli językowych (np. Ollama) oraz modeli chmurowych (np. OpenRouter).
- **Ogólny agent, doklejane możliwości**: Rdzeń nie zna żadnej konkretnej domeny; możliwości (dziś: smart home) dochodzą jako addony i integracje rejestrowane w kompozycji aplikacji.
- **Czas Rzeczywisty**: Strumieniowanie odpowiedzi w czasie rzeczywistym przez **SSE** oraz asynchroniczną magistralę zdarzeń (`EventBus`). Dwukierunkowe **WebSockets** są **planowane** — w kodzie nie ma dziś żadnego endpointu WS.
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
│   └── server/       # Główna usługa serwera Regis (bramka REST/SSE, kernel, addony, integracje, Web UI)
├── pyproject.toml    # Główna konfiguracja workspace, grupy dev (pytest, anyio) oraz pytest
└── README.md         # Wprowadzenie do projektu
```

### Struktura wewnętrzna usługi `services/server/src/server/`:

```text
server/
├── agent/          # WARSTWA 0 — Kernel: "umysł" agenta
│   ├── engine.py     # AgentEngine: pętla ReAct, agregacja addonów, sesje
│   ├── addon_contract.py  # AddonProvider (Protocol) — jedyna wiedza kernela o addonach
│   ├── backend/      # Dostawcy LLM + typy narzędzi (ToolDefinition/ToolCallRequest/ToolResult)
│   ├── context/      # ContextBuilder
│   ├── memory/       # MemoryManager
│   └── prompts/      # PromptStore
├── addons/         # WARSTWA 1 — Addony: domeny możliwości agenta
│   ├── base.py       # BaseTool — wspólna infrastruktura dla dowolnego addonu
│   └── smart_home/   # Addon Smart Home (Device, DeviceGroup, narzędzia LLM, CRUD)
├── integrations/   # WARSTWA 2 — Integracje: konkretne implementacje kontraktów addonów
│   └── home_assistant.py  # HomeAssistantIntegration + TYPE_NAME/SCHEMA/create()
├── network/        # Bramka FastAPI i routery REST/SSE
├── web/            # Wbudowana konsola SPA (HTML/CSS/JS)
├── config.py       # Settings (ConfigStore)
├── events.py       # ServerEventType
└── main.py         # Kompozycja aplikacji: wpina addony i rejestruje integracje
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
                                   | REST / SSE Streaming
                                   v
+-----------------------------------------------------------------------+
|                         WARSTWA SIECIOWA (GATEWAY)                    |
|                services/server/src/server/network (FastAPI)           |
+-----------------------------------------------------------------------+
                     |                                    |
                     v                                    v
+------------------------------------------+  +-------------------------+
|   WARSTWA 0 — KERNEL AGENTA              |  |  WARSTWA WSPÓŁNA        |
|  services/server/src/server/agent        |  |  packages/shared        |
|  - AgentEngine (pętla ReAct)             |  |  - EventBus             |
|  - MemoryManager (Session storage)       |  |  - ConfigStore          |
|  - ContextBuilder                        |  |  - Contracts (DTOs)     |
|  - AddonProvider (kontrakt addonów)      |  |  - Logging              |
+------------------------------------------+  +-------------------------+
        |                        |                        ^
        v                        v                        |
+------------------------+  +------------------------------------------+
| WARSTWA DOSTAWCÓW LLM  |  |  WARSTWA 1 — ADDONY                      |
| agent/backend          |  |  services/server/src/server/addons       |
| - BackendRegistry      |  |  - BaseTool (wspólna infrastruktura)     |
| - BaseLLMProvider      |  |  - SmartHomeAddon (Device, DeviceGroup,  |
|   (Ollama, OpenRouter) |  |    narzędzia LLM, DeviceIntegration)     |
+------------------------+  +------------------------------------------+
                                              |
                                              v
                            +------------------------------------------+
                            |  WARSTWA 2 — INTEGRACJE                  |
                            |  services/server/src/server/integrations |
                            |  - HomeAssistantIntegration              |
                            +------------------------------------------+
```

### Zasada kierunku zależności (fundament architektury)

**Żadna warstwa nie zna z góry konkretnych implementacji warstwy poniżej — te
rejestrują się same, jawnie, w kompozycji aplikacji (`main.py`).**

- Kernel nigdy nie importuje niczego z `addons/` ani `integrations/`. Zna
  wyłącznie protokół `AddonProvider` (`build_tools() -> (ToolDefinition[], dispatch)`).
  Lista addonów jest wstrzykiwana do `AgentEngine(addons=[...])` z `main.py`.
- Addon nigdy nie importuje niczego z `integrations/` ani nie zna nazwy żadnej
  konkretnej integracji. Integracje rejestrują się przez
  `SmartHomeAddon.register_integration_type(TYPE_NAME, create, SCHEMA)`,
  wołane jawnie z `main.py`.

Dzięki temu Regis pozostaje **ogólnym agentem**, a smart home (i Home Assistant
jako jedna z możliwych jego realizacji) jest tylko *narzędziem, którego agent
może użyć* — nie integralną częścią tego, czym agent jest.

### Trzy poziomy odpowiedzi na pytanie "czym jest narzędzie"

- **Kernel definiuje czym JEST narzędzie** — `ToolDefinition` (nazwa, opis,
  JSON Schema parametrów), `ToolCallRequest` (żądanie wywołania od LLM),
  `ToolResult` (wynik) w `agent/backend/providers/base.py`.
- **Addon deklaruje JAKIE narzędzia istnieją** — `build_tools()` zwraca
  konkretne instancje `ToolDefinition` (`list_devices`, `get_state`,
  `turn_on`, `turn_off`), identyczne niezależnie od liczby integracji.
- **Integracja wypełnia je TREŚCIĄ** — `DeviceIntegration.list_devices()`
  i `invoke()` dostarczają realne urządzenia i egzekucję.

### 3.1 Warstwa Sieciowa (`services/server/src/server/network`)
- **FastAPI Gateway (`gateway.py`) i zmodularyzowane routery (`routes/`)**: Obsługują punkty końcowe REST i SSE API v1 z podziałem na dedykowane pod-routery:
  - **`routes/health.py`**: Status zdrowia bramki i modułów (`GET /api/v1/health`).
  - **`routes/providers.py`**: Konfiguracja i zarządzenie dostawcami LLM (`GET/POST/PUT/DELETE /api/v1/llm/providers/*`, schemas).
  - **`routes/chat.py`**: Interakcje synchroniczne, strumieniowanie SSE i anulowanie (`POST /api/v1/chat/*`).
  - **`routes/sessions.py`**: Zarządzanie i historia sesji konwersacji (`GET/POST/DELETE /api/v1/chat/sessions/*`).
  - **`routes/prompts.py`**: CRUD promptów systemowych wraz z aktywacją (`GET/POST/PUT/DELETE /api/v1/agent/prompts/*`, `PUT /{id}/activate`).
  - **`routes/integrations.py`**: Konfiguracja integracji i grup urządzeń (`GET/POST/PUT/DELETE /api/v1/integrations/*` oraz `/api/v1/integrations/groups/*`).
- **Gateway (`gateway.py`)**: Serwuje wbudowaną konsolę WWW (SPA) oraz rejestruje centralny router API v1 (`create_api_router`). W modelu pojedynczej usługi strumieniowanie tokenów do konsoli realizowane jest przez protokół **SSE**. Dwukierunkowa bramka **WebSockets** (`ws://127.0.0.1:8000/ws`) jest wyłącznie **zaplanowana** jako punkt komunikacji w architekturze rozproszonej z wieloma usługami satelitarnymi — `gateway.py` nie rejestruje dziś żadnego endpointu WS.
- **Kompozycja aplikacji**: Instancja FastAPI powstaje w `create_gateway_app()`, wołanym z asynchronicznej funkcji `main()` po inicjalizacji rejestru backendów, `PromptStore` i addonów. Moduł `server.main` **nie eksportuje** modułowego obiektu `app`, więc uruchomienie przez `uvicorn server.main:app --reload` nie jest możliwe (patrz `docs/onboarding.md`, sekcja 4).

### 3.2 Warstwa 0 — Kernel Agenta (`services/server/src/server/agent`)
- **`AgentEngine` (`engine.py`)**: Serce orkiestracji Systemu Regis. Realizuje **pełną pętlę agentyczną (ReAct)** — jeśli LLM zażąda wywołania narzędzia, wynik wraca do niego jako kolejna wiadomość i generacja jest kontynuowana, aż model zwróci odpowiedź finalną lub zostanie przekroczony `max_tool_iterations` (domyślnie 8). Kontroluje aktywne zadania konwersacyjne (`_active_tasks`), zarządza cyklem życia sesji oraz udostępnia metody `interact_stream` i `cancel_interaction`.
- **`addon_contract.py`**: Definicja `AddonProvider` (`typing.Protocol`) i `ToolDispatch` — **jedyna wiedza kernela o istnieniu addonów**. `AgentEngine._build_aggregated_tools()` scala narzędzia ze wszystkich wpiętych addonów; przy kolizji nazw narzędzie późniejszego addonu jest logowane jako błąd i pomijane (bez cichego nadpisania).
- **`MemoryManager` (`memory/session.py`)**: Odpowiada za utrwalanie historii rozmów per sesja na dysku (`data/sessions/*.json`). Do pamięci trafia **wyłącznie finalny tekst odpowiedzi** — pośrednie wiadomości `assistant`/`tool` z pętli ReAct żyją tylko w pamięci na czas jednej interakcji.
- **`ContextBuilder` (`context/builder.py`)**: Komponuje ostateczny prompt dla LLM, łącząc instrukcje systemowe z historią sesji. Przycina historię do `max_history_messages` najnowszych wiadomości (domyślnie 40, konfigurowalne w `settings.json`), by uniknąć przekroczenia limitu kontekstu modelu w długich konwersacjach. Przycinanie działa na podstawie liczby wiadomości, nie realnego zliczania tokenów. Parametr `tools_available` warunkowo dokleja jedno neutralne zdanie o dostępności narzędzi — nigdy nie wymienia ich nazw ani pochodzenia.
- **`PromptStore` (`prompts/store.py`)**: Magazyn promptów systemowych (`data/prompts/*.json`) z wyborem aktywnego promptu (`data/active_prompt.json`). Usunięcie aktywnego promptu jest zablokowane; gdy nie da się wczytać żadnego, `ContextBuilder` używa `DEFAULT_SYSTEM_PROMPT` jako fallbacku.
  > **Pułapka**: `ensure_defaults()` tworzy domyślny prompt **tylko gdy katalog `data/prompts/` jest pusty**. Późniejsza zmiana `DEFAULT_SYSTEM_PROMPT` w kodzie **nie aktualizuje** już zapisanego pliku — treść, którą faktycznie dostaje LLM, żyje na dysku i zmienia się wyłącznie przez UI/REST. Przy zmianach możliwości agenta (np. włączeniu tool callingu) trzeba zaktualizować aktywny prompt osobno.

### 3.3 Warstwa Dostawców LLM (`services/server/src/server/agent/backend`)
- **`BaseLLMProvider` (`providers/base.py`)**: Interfejs abstrakcyjny definiujący metodę `generate_stream(messages, tools)`, która yielduje `str` (fragment tekstu) **albo** `ToolCallRequest` (kompletne żądanie wywołania narzędzia). Cała złożoność formatu API konkretnego dostawcy (OpenRouter: akumulacja fragmentarycznych `delta.tool_calls` z SSE; Ollama: kompletne `tool_calls` w jednym komunikacie) jest ukryta wewnątrz providera — kernel operuje wyłącznie na abstrakcyjnych typach. Oba dostępne backendy wspierają tool calling.
- **`ToolDefinition` / `ToolCallRequest` / `ToolResult` (`providers/base.py`)**: Typy definiujące, **czym jest narzędzie** w całym systemie (patrz sekcja 3 powyżej).
- **`BackendRegistry` (`registry.py`)**: Dynamiczny rejestr dostawców modeli z możliwością płynnego przełączania aktywnego backendu (np. z lokalnego `OllamaProvider` na chmurowy `OpenRouterProvider`).

### 3.4 Warstwa 1 — Addony (`services/server/src/server/addons`)
- **`BaseTool` (`base.py`)**: Wspólna, domenowo-neutralna abstrakcja narzędzia dostępna dla dowolnego addonu. Kernel jej nie zna — widzi wyłącznie finalną listę `ToolDefinition`.
- **`SmartHomeAddon` (`smart_home/addon.py`)**: Addon domeny smart home. Spełnia `AddonProvider` strukturalnie (metoda `build_tools()`). Zarządza instancjami integracji i grupami urządzeń jako plikami JSON (`data/addons/smart_home/{integrations,groups}/*.json`). Udostępnia `register_integration_type()` — mechanizm samorejestracji integracji.
- **`Device` / `DeviceGroup` / `DeviceRegistry` (`smart_home/devices.py`)**: Domenowy słownik addonu. `DeviceRegistry.resolve()` to **jedyne miejsce w systemie z logiką dopasowania nazwy** urządzenia lub grupy (rozstrzyga też niejednoznaczności) — integracje tego nie duplikują. `Device.area` jest luźnym, opcjonalnym tagiem bez rejestru (świadomie **nie** ma rdzennego pojęcia "pokoju" — patrz sekcja 5).
- **Narzędzia LLM (`smart_home/tools.py`)**: `list_devices`, `get_state`, `turn_on`, `turn_off` — zaimplementowane **raz**, współdzielone przez wszystkie zarejestrowane integracje. Działają zarówno na pojedynczym urządzeniu, jak i na całej grupie (z agregacją częściowych niepowodzeń). Nazwy i opisy narzędzi nigdy nie ujawniają konkretnej integracji.
- **`DeviceIntegration` (`smart_home/base.py`)**: Kontrakt Warstwy 2 zdefiniowany przez addon.

### 3.5 Warstwa 2 — Integracje (`services/server/src/server/integrations`)
- **`HomeAssistantIntegration` (`home_assistant.py`)**: Implementacja `DeviceIntegration` komunikująca się z REST API Home Assistant. Cała wiedza o formacie danych HA (`entity_id`, `domain.service`, atrybuty encji) jest zamknięta w tej klasie. Moduł eksportuje `TYPE_NAME`, `SCHEMA` i `create()` — komplet danych potrzebnych do samorejestracji w addonie.

### 3.6 Warstwa Wspólna (`packages/shared/src/shared`)
- **`ConfigStore` (`config.py`)**: Centralny zarządca persystentnej konfiguracji w formacie JSON z automatyczną walidacją i domyślnymi wartościami.
- **`EventBus` (`event_bus.py`)**: Asynchroniczna magistrala zdarzeń pub/sub (`subscribe`/`publish`). **W pełni wpięta w przepływ strumieniowania** — `AgentEngine` publikuje zdarzenia `ServerEventType.CHAT_CHUNK/DONE/ERROR/CANCELLED`, a `interact_stream` subskrybuje je i tłumaczy z powrotem na strumień tokenów dla wywołującego. Dzięki temu rdzeń nie zna bezpośrednio odbiorców (SSE dziś, WebSockets satelitów w przyszłości).
- **`contracts.py`**: Definicje obiektów transferu danych (DTO) współdzielonych przez serwer i konsolę WWW:
  - **System**: `HealthResponse`.
  - **Dostawcy LLM**: `LLMProviderDTO`, `LLMProviderListResponse`, `SelectLLMProviderRequest`, `CreateLLMProviderRequest` oraz generyczna specyfikacja opcji (`ProviderOptionSpec`, `ProviderTypeSpecDTO`, `ProviderMetadataResponse`) — ta sama, której używają też typy integracji.
  - **Czat i sesje**: `ChatMessageDTO`, `SendChatMessageRequest`, `ChatResponseDTO`, `ChatSessionSummaryDTO`, `ChatSessionHistoryResponse`, `ChatSessionListResponse`, `CancelChatApiRequest`.
  - **Prompty systemowe**: `PromptDTO`, `PromptListResponse`, `CreatePromptRequest`, `UpdatePromptRequest`.
  - **Integracje i grupy urządzeń**: `IntegrationDTO`, `IntegrationListResponse`, `CreateIntegrationRequest`, `UpdateIntegrationRequest`, `DeviceGroupDTO`, `DeviceGroupListResponse`, `CreateDeviceGroupRequest`, `UpdateDeviceGroupRequest`.
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
       |                       |                     |--- build_tools (agregacja addonów)    |                 |
       |                       |                     |--- build_messages ------------------->|                 |
       |                       |                     |--- generate_stream(tools) ----------->|                 |
       |                       |                     |--- publish CHAT_CHUNK ---------------------------------->|
       |<-- sse data chunk ----|<-- yield chunk -----|<-- (subskrypcja EventBus) ------------------------------|
       |                       |                     |--- add_assistant_msg -->|             |                 |
       |                       |                     |--- publish CHAT_DONE ----------------------------------->|
       |<-- sse data [DONE] ---|<--------------------|                   |                   |                 |
```

### 4.2 Pętla Agentyczna (ReAct — Tool Calling)
```text
AgentEngine            LLM Provider          Addon (build_tools)      Integracja (invoke)
     |                       |                        |                        |
     |--- build_tools() ---------------------------->|                        |
     |                       |                        |--- list_devices() --->|
     |<-- [ToolDefinition], dispatch ----------------|<-- [Device] ----------|
     |                       |                        |                        |
     |--- generate_stream(messages, tools) --------->|                        |
     |<-- ToolCallRequest("turn_on", {...}) ---------|                        |
     |                       |                        |                        |
     |--- dispatch("turn_on", args) ---------------->|                        |
     |                       |                        |--- invoke(id, cap) -->|
     |<-- ToolResult -------------------------------|<-- ToolResult ---------|
     |                       |                        |                        |
     | [append assistant(tool_calls) + tool(result) do working_messages]      |
     |--- generate_stream(messages+wyniki, tools) -->|                        |
     |<-- "Włączyłem światło." (tekst finalny) ------|                        |
     |                       |                        |                        |
     | [break — brak dalszych wywołań; tylko finalny tekst trafia do pamięci] |
```
> Pętla powtarza się maksymalnie `max_tool_iterations` razy (domyślnie 8).
> Wywołania narzędzi wykonują się **automatycznie, bez potwierdzenia użytkownika**.

### 4.3 Przepływ Przerwania / Anulowania Zapytania
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
2. **Dodawanie nowych addonów i integracji**: Nowy addon = klasa z metodą `build_tools()` w `addons/`, wpięta do `AgentEngine(addons=[...])` w `main.py`. Nowa integracja = implementacja kontraktu danego addonu w `integrations/`, eksportująca `TYPE_NAME`/`SCHEMA`/`create()` i zarejestrowana w `main.py`. **Żadna z tych operacji nie wymaga zmiany kernela ani istniejących addonów.**
3. **Model dystrybucji**: Nic ponad kernel nie jest architektonicznie uprzywilejowane — podział na "wbudowane" i "pobieralne" byłby decyzją dystrybucyjną, nie granicą kodu. Obecnie wszystko żyje w jednym pakiecie z jawną rejestracją w `main.py`; dynamiczne ładowanie pluginów, manifesty i sandboxing są **świadomie odłożone** (brak realnego przypadku użycia — YAGNI). Granica `AddonProvider` sprawia, że dodanie loadera w przyszłości nie wymaga przepisywania kernela.

### Świadome decyzje projektowe (nie zmieniać bez ponownej analizy)

- **Brak rdzennego pojęcia "pokoju" (`Room`)**: Narzucałoby kernelowi/addonowi założenie „świat = dom z pokojami”, podczas gdy smart home jest tylko jedną z możliwych domen agenta. `Device.area` pozostaje luźnym tagiem bez rejestru. Świadomość przestrzenna będzie własnością przyszłego systemu satelitów (satelita deklaruje swoją lokalizację), a skorelowanie jej z urządzeniami należy do LLM, nie do sztywnej logiki serwera.
- **`DeviceGroup` należy do addonu, nie do kernela**: Model grupowania jest ściśle związany z `invoke`/capability tej konkretnej domeny; generalizacja bez drugiego przypadku użycia byłaby przedwczesna.
- **Integracje żyją w `server/integrations/`, nie wewnątrz addonu**: Zagnieżdżenie (`addons/smart_home/integrations/home_assistant.py`) sugerowałoby, że integracja jest częścią addonu i należy do niego jako implementacja. Tymczasem zależność biegnie w drugą stronę: to integracja zna kontrakt addonu (`DeviceIntegration`), a addon nie zna żadnej integracji. Katalog najwyższego poziomu utrzymuje tę asymetrię widoczną w strukturze plików i zostawia miejsce na integracje obsługujące kontrakty kilku addonów naraz.
- **Brak potwierdzeń dla akcji z efektami ubocznymi**: Narzędzia wykonują się automatycznie w pętli ReAct.
- **Zapis decyzji: ta sekcja zamiast osobnych ADR-ów**: Uzasadnienia mieszkają tam, gdzie i tak czyta się architekturę. Osobny katalog `docs/adr/` duplikowałby te treści i rozjeżdżał się z manifestem — w projekcie jednoosobowym to koszt bez odbiorcy. Zmieniasz jedną z powyższych decyzji? Zaktualizuj wpis, nie dopisuj nowego dokumentu obok.

### Zaplanowane, jeszcze niezaimplementowane

1. **Ręczna deklaracja urządzeń + discovery w UI**: Obecnie `HomeAssistantIntegration.list_devices()` pobiera **wszystkie** encje z `/api/states` bez filtrowania. Docelowo użytkownik ma ręcznie wybierać encje z listy podanej przez endpoint discovery, widoczne w zakładce integracji.
2. **Zakładka „Integracje” w Web Console**: Backend REST jest kompletny (`/api/v1/integrations/*` + grupy); brakuje warstwy SPA analogicznej do istniejących widoków `settings`/`agents`.
3. **Widoczność wywołań narzędzi w UI**: `EventBus` jest gotowy na rozszerzenie o `TOOL_CALL_START/RESULT`; obecnie wywołania trafiają wyłącznie do logów.
4. **Pamięć Długoterminowa i Wektorowa**: Planowana integracja modułów pamięci wektorowej i semantycznej w usłudze `server`.
5. **Skalowanie Usług Rozproszonych & WebSockets**: Przygotowanie infrastruktury `services/` pod uruchamianie dedykowanych mikrousług specjalistycznych (satelitów) w sieci lokalnej i ich komunikacji via WebSockets.
