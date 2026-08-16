# Manifest Architektoniczny Systemu Regis

## 1. Wizja i Cel Systemu Regis

**System Regis** to modularna platforma usług rozproszonych komunikujących się w sieci lokalnej, przeznaczona do orkiestracji i wykonywania zadań przez inteligentnych agentów AI.

Kluczowe założenia architektoniczne Systemu Regis:
- **Lokalność i Rozproszenie**: Usługi działają wydajnie w sieci lokalnej z pełną kontrolą nad prywatnością danych i przepływem informacji. *(Dziś: jedna usługa `services/server`; wielousługowość to kierunek, nie stan obecny — patrz sekcja 5.)*
- **Hybrydowość modeli LLM**: Przezroczysta obsługa lokalnych modeli językowych (np. Ollama) oraz modeli chmurowych (np. OpenRouter).
- **Ogólny agent, doklejane możliwości**: Rdzeń nie zna żadnej konkretnej domeny; możliwości (dziś: smart home) dochodzą jako pluginy i integracje rejestrowane w kompozycji aplikacji, agregowane co turę przez `Gateway`.
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
│   └── specs/        # Efemeryczne briefy implementacyjne (cykl życia: AGENTS.md, sekcja "Dokumentacja")
├── packages/         # Wspólne pakiety kodowe
│   └── shared/       # Paczka shared (ConfigStore, EventBus, DTO, logging)
├── services/         # Niezależne usługi sieciowe
│   └── server/       # Główna usługa serwera Regis (bramka REST/SSE, kernel, pluginy, integracje, Web UI)
├── pyproject.toml    # Główna konfiguracja workspace, grupy dev (pytest, anyio) oraz pytest
└── README.md         # Wprowadzenie do projektu
```

### Struktura wewnętrzna usługi `services/server/src/server/`:

```text
server/
├── agent/          # WARSTWA 0 — Kernel: "umysł" agenta
│   ├── engine.py     # AgentEngine: pętla ReAct, sesje
│   ├── gateway.py     # Gateway — jedyny agregator: pluginy → 3 kanały, sekwencyjnie
│   ├── plugin_contract.py  # PluginProvider (Protocol) + EntitySpec/EntityCapability/Fact — jedyna wiedza Gateway o pluginach
│   ├── backend/      # Dostawcy LLM + typy narzędzi (ToolDefinition/ToolCallRequest/ToolResult)
│   ├── context/      # ContextBuilder
│   ├── memory/       # MemoryManager
│   └── prompts/      # PromptStore
├── plugins/        # WARSTWA 1 — Pluginy: domeny możliwości agenta
│   ├── smart_home/   # Plugin Smart Home (Device, DeviceGroup, narzędzia LLM, CRUD)
│   └── datetime_plugin.py  # DateTimePlugin — narzędzie get_time + bliźniaczy Fakt (wizja, sekcja 4.5)
├── integrations/   # WARSTWA 2 — Integracje: konkretne implementacje kontraktów pluginów
│   └── home_assistant.py  # HomeAssistantIntegration + TYPE_NAME/SCHEMA/create()
├── network/        # Bramka FastAPI i routery REST/SSE
├── web/            # Wbudowana konsola SPA (HTML/CSS/JS)
├── config.py       # Settings (ConfigStore)
├── events.py       # ServerEventType
└── main.py         # Kompozycja aplikacji: wpina pluginy do Gateway
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
|  - Gateway (agregator 3 kanałów treści)  |  |  - Logging              |
|  - PluginProvider                        |  |                         |
+------------------------------------------+  +-------------------------+
        |                        |                        ^
        v                        v                        |
+------------------------+  +------------------------------------------+
| WARSTWA DOSTAWCÓW LLM  |  |  WARSTWA 1 — PLUGINY                     |
| agent/backend          |  |  services/server/src/server/plugins      |
| - BackendRegistry      |  |  - SmartHomePlugin (Device, DeviceGroup, |
| - BaseLLMProvider      |  |    narzędzia LLM, DeviceIntegration,     |
|   (Ollama, OpenRouter) |  |    opaque ID entities dla Gateway)       |
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
rejestrują się same, jawnie, w kompozycji aplikacji (`main.py`). Każda warstwa
zna wyłącznie *kształt* tego, co dostaje od warstwy pod spodem — nigdy treść
ani pochodzenie.**

- Kernel nigdy nie importuje niczego z `plugins/` ani `integrations/`. Zna
  wyłącznie protokół `PluginProvider` (`build(facts) -> PluginContribution`),
  zdefiniowany w `agent/plugin_contract.py`. `Gateway` (`agent/gateway.py`) —
  jedyny agregator, zawsze budowany od zera co turę, w jednym sekwencyjnym
  przebiegu w kolejności rejestracji — dostaje listę pluginów wstrzykniętą
  z `main.py`, wpięty następnie do `AgentEngine(gateway=...)`.
- Plugin nigdy nie importuje niczego z `integrations/` ani nie zna nazwy żadnej
  konkretnej integracji. Integracje rejestrują się przez
  `SmartHomePlugin.register_integration_type(TYPE_NAME, create, SCHEMA)`,
  wołane jawnie z `main.py`.
- Gateway nigdy nie rozmawia bezpośrednio z żadną integracją — wyłącznie
  z Pluginami, które w pełni orkiestrują swoje integracje wewnętrznie
  (włącznie z rozwiązywaniem grup urządzeń, patrz sekcja 3.4).

Dzięki temu Regis pozostaje **ogólnym agentem**, a smart home (i Home Assistant
jako jedna z możliwych jego realizacji) jest tylko *narzędziem, którego agent
może użyć* — nie integralną częścią tego, czym agent jest.

### Trzy kanały treści agenta i adresowanie po opaque ID

Gateway buduje co turę trzy płaskie kanały, przekazywane do `ContextBuilder`:

| Kanał | Co zawiera | Kto buduje |
|---|---|---|
| **Narzędzia** | `ToolDefinition[]` (nazwa, opis, JSON Schema parametrów) | Pluginy, przez `PluginProvider` |
| **Encje** | `EntitySpec[]` — rzeczy do interakcji z opaque ID i etykietami możliwości, w tym już rozwiązane grupy | Pluginy |
| **Fakty** | `Fact[]` — kontekst niezwiązany z żadnym narzędziem, zawsze z bliźniaczym narzędziem (dziś: aktualna data/godzina) | Pluginy, opcjonalnie |

Agent adresuje encje wyłącznie przez `entity_id` — opaque, nieprzezroczysty
identyfikator nadany przez Gateway (skrót SHA-256 z tożsamości pluginu +
wewnętrznego odniesienia nadanego przez ten plugin), nigdy po przyjaznej
nazwie ani natywnym ID integracji. Ten sam skrót jest deterministyczny —
Gateway może więc budować wszystko od zera co turę, a identyfikator mimo to
pozostaje stabilny w historii rozmowy. Gateway tłumaczy `entity_id` z opaque
na wewnętrzny ref pluginu tuż przed wywołaniem jego `dispatch()` — plugin
nigdy nie widzi opaque ID.

### 3.1 Warstwa Sieciowa (`services/server/src/server/network`)
- **FastAPI Gateway (`gateway.py`) i zmodularyzowane routery (`routes/`)**: Obsługują punkty końcowe REST i SSE API v1 z podziałem na dedykowane pod-routery:
  - **`routes/health.py`**: Status zdrowia bramki i modułów (`GET /api/v1/health`).
  - **`routes/providers.py`**: Konfiguracja i zarządzenie dostawcami LLM (`GET/POST/PUT/DELETE /api/v1/llm/providers/*`, schemas).
  - **`routes/chat.py`**: Interakcje synchroniczne, strumieniowanie SSE i anulowanie (`POST /api/v1/chat/*`).
  - **`routes/sessions.py`**: Zarządzanie i historia sesji konwersacji (`GET/POST/DELETE /api/v1/chat/sessions/*`).
  - **`routes/prompts.py`**: CRUD promptów systemowych wraz z aktywacją (`GET/POST/PUT/DELETE /api/v1/agent/prompts/*`, `PUT /{id}/activate`).
  - **`routes/integrations.py`**: Konfiguracja integracji i grup urządzeń (`GET/POST/PUT/DELETE /api/v1/integrations/*` oraz `/api/v1/integrations/groups/*`).
- **Gateway (`gateway.py`)**: Serwuje wbudowaną konsolę WWW (SPA) oraz rejestruje centralny router API v1 (`create_api_router`). W modelu pojedynczej usługi strumieniowanie tokenów do konsoli realizowane jest przez protokół **SSE**. Dwukierunkowa bramka **WebSockets** (`ws://127.0.0.1:8000/ws`) jest wyłącznie **zaplanowana** jako punkt komunikacji w architekturze rozproszonej z wieloma usługami satelitarnymi — `gateway.py` nie rejestruje dziś żadnego endpointu WS.
- **Kompozycja aplikacji**: Instancja FastAPI powstaje w `create_gateway_app()`, wołanym z asynchronicznej funkcji `main()` po inicjalizacji rejestru backendów, `PromptStore` i pluginów. Moduł `server.main` **nie eksportuje** modułowego obiektu `app`, więc uruchomienie przez `uvicorn server.main:app --reload` nie jest możliwe (patrz `docs/onboarding.md`, sekcja 4).

### 3.2 Warstwa 0 — Kernel Agenta (`services/server/src/server/agent`)
- **`AgentEngine` (`engine.py`)**: Serce orkiestracji Systemu Regis. Realizuje **pełną pętlę agentyczną (ReAct)** — jeśli LLM zażąda wywołania narzędzia, wynik wraca do niego jako kolejna wiadomość i generacja jest kontynuowana, aż model zwróci odpowiedź finalną lub zostanie przekroczony `max_tool_iterations` (domyślnie 8). Kontroluje aktywne zadania konwersacyjne (`_active_tasks`), zarządza cyklem życia sesji oraz udostępnia metody `interact_stream` i `cancel_interaction`. Na początku każdej interakcji woła `Gateway.build()` (nigdy cache'owane) i przekazuje jego trzy kanały (narzędzia, encje, fakty) do `ContextBuilder`.
- **`gateway.py`**: `Gateway` — jedyny agregator kernela, budujący pluginy sekwencyjnie w kolejności rejestracji (jeden przebieg), przekazując każdemu kolejnemu Fakty zebrane od pluginów zbudowanych wcześniej w tej samej turze, nadający encjom opaque ID i budujący tabelę routingu `opaque_id -> (plugin, wewnętrzny ref)` na tę turę (patrz sekcja "Trzy kanały treści agenta" wyżej).
- **`plugin_contract.py`**: Definicje `PluginProvider` (`typing.Protocol`), `EntitySpec`/`EntityCapability`/`PluginContribution`/`Fact` — **jedyna wiedza Gateway o istnieniu pluginów**. Fakty są opcjonalnym polem `PluginContribution`, na równi z narzędziami i encjami — nie ma osobnej kategorii "dostawcy kontekstu" (wizja, `docs/specs/agent-context-architecture-vision.md`, sekcja 2). Przy kolizji nazw narzędzi między dwoma pluginami narzędzie późniejszego pluginu jest logowane jako błąd i pomijane (bez cichego nadpisania) — identyczna polityka jak dawniej na poziomie kernela.
- **`MemoryManager` (`memory/session.py`)**: Odpowiada za utrwalanie historii rozmów per sesja na dysku (`data/sessions/*.json`). Do pamięci trafia **wyłącznie finalny tekst odpowiedzi** — pośrednie wiadomości `assistant`/`tool` z pętli ReAct żyją tylko w pamięci na czas jednej interakcji.
- **`ContextBuilder` (`context/builder.py`)**: Komponuje ostateczny prompt dla LLM, łącząc instrukcje systemowe z historią sesji. Przycina historię do `max_history_messages` najnowszych wiadomości (domyślnie 40, konfigurowalne w `settings.json`), by uniknąć przekroczenia limitu kontekstu modelu w długich konwersacjach. Przycinanie działa na podstawie liczby wiadomości, nie realnego zliczania tokenów. Parametr `tools_available` warunkowo dokleja jedno neutralne zdanie o dostępności narzędzi — nigdy nie wymienia ich nazw ani pochodzenia. Parametry `entities`/`facts` (kanały z `Gateway.build()`) są formatowane w pełni generycznie — kernel zna wyłącznie kształt `EntitySpec`/`Fact` z Kontraktu, nigdy domeny, która je wypełniła.
- **`PromptStore` (`prompts/store.py`)**: Magazyn promptów systemowych (`data/prompts/*.json`) z wyborem aktywnego promptu (`data/active_prompt.json`). Usunięcie aktywnego promptu jest zablokowane; gdy nie da się wczytać żadnego, `ContextBuilder` używa `DEFAULT_SYSTEM_PROMPT` jako fallbacku.
  > **Pułapka**: `ensure_defaults()` tworzy domyślny prompt **tylko gdy katalog `data/prompts/` jest pusty**. Późniejsza zmiana `DEFAULT_SYSTEM_PROMPT` w kodzie **nie aktualizuje** już zapisanego pliku — treść, którą faktycznie dostaje LLM, żyje na dysku i zmienia się wyłącznie przez UI/REST. Przy zmianach możliwości agenta (np. włączeniu tool callingu) trzeba zaktualizować aktywny prompt osobno.

### 3.3 Warstwa Dostawców LLM (`services/server/src/server/agent/backend`)
- **`BaseLLMProvider` (`providers/base.py`)**: Interfejs abstrakcyjny definiujący metodę `generate_stream(messages, tools)`, która yielduje `str` (fragment tekstu) **albo** `ToolCallRequest` (kompletne żądanie wywołania narzędzia). Cała złożoność formatu API konkretnego dostawcy (OpenRouter: akumulacja fragmentarycznych `delta.tool_calls` z SSE; Ollama: kompletne `tool_calls` w jednym komunikacie) jest ukryta wewnątrz providera — kernel operuje wyłącznie na abstrakcyjnych typach. Oba dostępne backendy wspierają tool calling.
- **`ToolDefinition` / `ToolCallRequest` / `ToolResult` (`providers/base.py`)**: Typy definiujące, **czym jest narzędzie** w całym systemie (patrz sekcja 3 powyżej).
- **`BackendRegistry` (`registry.py`)**: Dynamiczny rejestr dostawców modeli z możliwością płynnego przełączania aktywnego backendu (np. z lokalnego `OllamaProvider` na chmurowy `OpenRouterProvider`).

### 3.4 Warstwa 1 — Pluginy (`services/server/src/server/plugins`)
- **`SmartHomePlugin` (`smart_home/plugin.py`)**: Plugin domeny smart home — jedyny byt widoczny dla `Gateway` w tej domenie. Spełnia `PluginProvider` strukturalnie (pole `plugin_id`, metoda `build(facts)`). Zarządza instancjami integracji i grupami urządzeń jako plikami JSON (`data/plugins/smart_home/{integrations,groups}/*.json`) — obie kategorie są prywatną, plugin-wide konfiguracją. Udostępnia `register_integration_type()` — mechanizm samorejestracji integracji. `build()` w pełni rozwiązuje grupy wewnętrznie i zwraca Gateway już spłaszczoną listę encji (`EntitySpec`), w której grupa jest nieodróżnialna z zewnątrz od pojedynczego urządzenia.
- **`Device` / `DeviceGroup` (`smart_home/models.py`)**: Domenowy słownik pluginu — konkretna realizacja generycznego `EntitySpec` z Kontraktu, pojęcie należące wyłącznie do tego pluginu (inny plugin miałby własne nazwy i pola). `Device.area` jest luźnym, opcjonalnym tagiem bez rejestru (świadomie **nie** ma rdzennego pojęcia "pokoju" — patrz sekcja 5) — bez konsumenta w postaci narzędzia LLM (nie ma już `list_devices` jako osobnego narzędzia, patrz niżej).
- **`DeviceRegistry` (`smart_home/registry.py`)**: Czysty magazyn urządzeń i grup na czas jednej interakcji (`get_device()`/`get_group()` po wewnętrznym ref). W przeciwieństwie do dawnego rejestru addonu **nie ma logiki dopasowania po nazwie** — agent adresuje encje wyłącznie przez opaque `entity_id` nadany przez Gateway, które ten tłumaczy z powrotem na wewnętrzny ref tuż przed wywołaniem pluginu.
- **Narzędzia LLM (`smart_home/tools.py`)**: `get_state`, `turn_on`, `turn_off` — zaimplementowane **raz**, współdzielone przez wszystkie zarejestrowane integracje, adresowane przez parametr `entity_id`. Działają zarówno na pojedynczym urządzeniu, jak i na całej grupie (z agregacją częściowych niepowodzeń, `SmartHomeToolExecutor._invoke_group`). Nazwy i opisy narzędzi nigdy nie ujawniają konkretnej integracji. `list_devices` **nie istnieje** jako osobne narzędzie — kanał Encji (sekcja "Trzy kanały treści agenta") dostarcza dokładnie tę samą informację (z opaque ID) automatycznie co turę.
- **`DeviceIntegration` (`smart_home/contract.py`)**: Kontrakt Warstwy 2, prywatna sprawa pluginu — nigdy widoczny dla Gateway ani agenta.
- **`DateTimePlugin` (`datetime_plugin.py`)**: Minimalny plugin dowodzący zasady symetrii Fakt↔narzędzie (wizja, sekcja 4.5) — jedno narzędzie (`get_time`) i jeden odpowiadający mu Fakt (`aktualna_data_i_godzina`), oba liczone z tego samego `datetime.now()` w jednym wywołaniu `build()`. Nie dostarcza żadnych encji.

### 3.5 Warstwa 2 — Integracje (`services/server/src/server/integrations`)
- **`HomeAssistantIntegration` (`home_assistant.py`)**: Implementacja `DeviceIntegration` komunikująca się z REST API Home Assistant. Cała wiedza o formacie danych HA (`entity_id`, `domain.service`, atrybuty encji) jest zamknięta w tej klasie. Moduł eksportuje `TYPE_NAME`, `SCHEMA` i `create()` — komplet danych potrzebnych do samorejestracji w pluginie.

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
       |                       |                     |--- Gateway.build() (od zera, co turę)  |                 |
       |                       |                     |--- build_messages (+encje, +fakty) --->|                 |
       |                       |                     |--- generate_stream(tools) ----------->|                 |
       |                       |                     |--- publish CHAT_CHUNK ---------------------------------->|
       |<-- sse data chunk ----|<-- yield chunk -----|<-- (subskrypcja EventBus) ------------------------------|
       |                       |                     |--- add_assistant_msg -->|             |                 |
       |                       |                     |--- publish CHAT_DONE ----------------------------------->|
       |<-- sse data [DONE] ---|<--------------------|                   |                   |                 |
```

### 4.2 Pętla Agentyczna (ReAct — Tool Calling)
```text
AgentEngine       Gateway            SmartHomePlugin (build)     Integracja (invoke)
     |                |                        |                        |
     |--- build() --->|                        |                        |
     |                |--- build(facts) ------>|                        |
     |                |                        |--- list_devices() --->|
     |                |<-- tools, entities* ---|<-- [Device] -----------|
     |                | (* id = wewnętrzny ref, nieopaque)               |
     |<-- tool_definitions, entities (opaque id), facts, dispatch -------|
     |                       |                        |                        |
     |--- generate_stream(messages+encje+fakty, tools) ----------------------->|
     |<-- ToolCallRequest("turn_on", {entity_id: <opaque>}) --------------------|
     |                |                        |                        |
     |--- dispatch("turn_on", {entity_id: <opaque>}) -->|                |
     |                | [tłumaczy opaque->native ref przez routing_table]|
     |                |--- dispatch("turn_on", {entity_id: <native>}) ->|
     |                |                        |--- invoke(id, cap) -->|
     |<-- ToolResult -------------------------|<-- ToolResult ---------|
     |                       |                        |                        |
     | [append assistant(tool_calls) + tool(result) do working_messages]      |
     |--- generate_stream(messages+wyniki, tools) --------------------------->|
     |<-- "Włączyłem światło." (tekst finalny) ---------------------------------|
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
2. **Dodawanie nowych pluginów i integracji**: Nowy plugin = klasa z polem `plugin_id` i metodą `build(facts)` w `plugins/`, wpięta do `Gateway(plugins=[...])` w `main.py`. Fakty nie mają osobnej kategorii — plugin, który chce proaktywnie dostarczyć kontekst, dopisuje `facts` do zwracanego `PluginContribution` obok narzędzi i encji, pamiętając o bliźniaczym narzędziu (wizja, sekcja 4.5). Nowa integracja = implementacja kontraktu danego pluginu w `integrations/`, eksportująca `TYPE_NAME`/`SCHEMA`/`create()` i zarejestrowana w `main.py`. **Żadna z tych operacji nie wymaga zmiany kernela ani istniejących pluginów.**
3. **Model dystrybucji**: Nic ponad kernel nie jest architektonicznie uprzywilejowane — podział na "wbudowane" i "pobieralne" byłby decyzją dystrybucyjną, nie granicą kodu. Obecnie wszystko żyje w jednym pakiecie z jawną rejestracją w `main.py`; dynamiczne ładowanie pluginów, manifesty i sandboxing są **świadomie odłożone** (brak realnego przypadku użycia — YAGNI). Granica `PluginProvider` sprawia, że dodanie loadera w przyszłości nie wymaga przepisywania kernela.

### Świadome decyzje projektowe (nie zmieniać bez ponownej analizy)

- **Brak rdzennego pojęcia "pokoju" (`Room`)**: Narzucałoby kernelowi/pluginowi założenie „świat = dom z pokojami”, podczas gdy smart home jest tylko jedną z możliwych domen agenta. `Device.area` pozostaje luźnym tagiem bez rejestru. Świadomość przestrzenna będzie własnością przyszłego pluginu obecności/lokalizacji, deklarującego swoją pozycję jako Fakt (wizja, sekcja 4.3), a skorelowanie jej z urządzeniami należy do LLM, nie do sztywnej logiki serwera.
- **`DeviceGroup` należy do pluginu, nie do kernela**: Model grupowania jest ściśle związany z `invoke`/capability tej konkretnej domeny i może przecinać granice integracji tego samego pluginu; generalizacja na poziom Gateway byłaby odtworzeniem kompozytora, którego architektura świadomie unika (wizja, sekcja 4.4 i 8).
- **Integracje żyją w `server/integrations/`, nie wewnątrz pluginu**: Zagnieżdżenie (`plugins/smart_home/integrations/home_assistant.py`) sugerowałoby, że integracja jest częścią pluginu i należy do niego jako implementacja. Tymczasem zależność biegnie w drugą stronę: to integracja zna kontrakt pluginu (`DeviceIntegration`), a plugin nie zna żadnej integracji. Katalog najwyższego poziomu utrzymuje tę asymetrię widoczną w strukturze plików i zostawia miejsce na integracje obsługujące kontrakty kilku pluginów naraz.
- **Adresowanie po opaque ID, nie po nazwie**: Dawne dopasowywanie po przyjaznej nazwie (`DeviceRegistry.resolve()`) było kruche (niejednoznaczności, literówki) i zdradzało integrację stojącą za urządzeniem, gdy nazwa trafiała do logów/promptu. Gateway nadaje deterministyczny, nieprzezroczysty `entity_id` — stabilny w historii rozmowy mimo budowania kontekstu od zera co turę (wizja, sekcja 4.2).
- **Brak potwierdzeń dla akcji z efektami ubocznymi**: Narzędzia wykonują się automatycznie w pętli ReAct.
- **Zapis decyzji: ta sekcja zamiast osobnych ADR-ów**: Uzasadnienia mieszkają tam, gdzie i tak czyta się architekturę. Osobny katalog `docs/adr/` duplikowałby te treści i rozjeżdżał się z manifestem — w projekcie jednoosobowym to koszt bez odbiorcy. Zmieniasz jedną z powyższych decyzji? Zaktualizuj wpis, nie dopisuj nowego dokumentu obok.

### Zaplanowane, jeszcze niezaimplementowane

1. **Ręczna deklaracja urządzeń + discovery w UI**: Obecnie `HomeAssistantIntegration.list_devices()` pobiera **wszystkie** encje z `/api/states` bez filtrowania. Docelowo użytkownik ma ręcznie wybierać encje z listy podanej przez endpoint discovery, widoczne w zakładce integracji.
2. **Zakładka „Integracje” w Web Console**: Backend REST jest kompletny (`/api/v1/integrations/*` + grupy); brakuje warstwy SPA analogicznej do istniejących widoków `settings`/`agents`.
3. **Widoczność wywołań narzędzi w UI**: `EventBus` jest gotowy na rozszerzenie o `TOOL_CALL_START/RESULT`; obecnie wywołania trafiają wyłącznie do logów.
4. **Pamięć Długoterminowa i Wektorowa**: Planowana integracja modułów pamięci wektorowej i semantycznej w usłudze `server`.
5. **Skalowanie Usług Rozproszonych & WebSockets**: Przygotowanie infrastruktury `services/` pod uruchamianie dedykowanych mikrousług specjalistycznych (satelitów) w sieci lokalnej i ich komunikacji via WebSockets.
