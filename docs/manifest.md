# Manifest Architektoniczny Systemu Regis

## 1. Wizja i Cel Systemu Regis

**System Regis** to modularna platforma usług rozproszonych komunikujących się w sieci lokalnej, przeznaczona do orkiestracji i wykonywania zadań przez inteligentnych agentów AI.

Kluczowe założenia architektoniczne Systemu Regis:
- **Lokalność i Rozproszenie**: Usługi działają wydajnie w sieci lokalnej z pełną kontrolą nad prywatnością danych i przepływem informacji. *(Dziś: jedna usługa `services/server`; wielousługowość to kierunek, nie stan obecny — patrz sekcja 5.)*
- **Hybrydowość modeli LLM**: Przezroczysta obsługa lokalnych modeli językowych (np. Ollama) oraz modeli chmurowych (np. OpenRouter).
- **Ogólny agent, doklejane możliwości**: Rdzeń nie zna żadnej konkretnej domeny; możliwości (dziś: Home Assistant, data/godzina) dochodzą jako Rozszerzenia rejestrowane w kompozycji aplikacji, agregowane co turę przez `Gateway`.
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
│   └── server/       # Główna usługa serwera Regis (bramka REST/SSE, kernel, rozszerzenia, Web UI)
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
├── extensions/     # WARSTWA 1 — Rozszerzenia: domeny możliwości agenta
│   ├── home_assistant/  # HomeAssistantExtension (Device, DeviceGroup, deklaracje, CRUD, routes)
│   ├── basic_tools/      # BasicToolsExtension — narzędzie get_time + bliźniaczy Fakt (wizja, sekcja 4.5)
│   └── _shared/          # ExtensionStateFileContent — wspólny model state.json (DRY, nie kontrakt)
├── network/        # Bramka FastAPI i routery REST/SSE
├── web/            # Wbudowana konsola SPA (HTML/CSS/JS)
├── config.py       # Settings (ConfigStore)
├── events.py       # ServerEventType
└── main.py         # Kompozycja aplikacji: wpina rozszerzenia do Gateway i do sieci (NetworkExtension)
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
| WARSTWA DOSTAWCÓW LLM  |  |  WARSTWA 1 — ROZSZERZENIA                |
| agent/backend          |  |  services/server/src/server/extensions   |
| - BackendRegistry      |  |  - HomeAssistantExtension (Device,       |
| - BaseLLMProvider      |  |    DeviceGroup, klient HA, deklaracje,   |
|   (Ollama, OpenRouter) |  |    opaque ID entities dla Gateway)       |
+------------------------+  |  - BasicToolsExtension (get_time)        |
                             +------------------------------------------+
```

### Zasada kierunku zależności (fundament architektury)

**Żadna warstwa nie zna z góry konkretnych implementacji warstwy poniżej — te
rejestrują się same, jawnie, w kompozycji aplikacji (`main.py`). Każda warstwa
zna wyłącznie *kształt* tego, co dostaje od warstwy pod spodem — nigdy treść
ani pochodzenie.**

- Kernel nigdy nie importuje niczego z `extensions/`. Zna wyłącznie protokół
  `PluginProvider` (`build(facts) -> PluginContribution`), zdefiniowany
  w `agent/plugin_contract.py`. `Gateway` (`agent/gateway.py`) — jedyny
  agregator, zawsze budowany od zera co turę, w jednym sekwencyjnym przebiegu
  w kolejności rejestracji — dostaje listę rozszerzeń wstrzykniętą z `main.py`,
  wpięty następnie do `AgentEngine(gateway=...)`.
- Sieć (`network/gateway.py`) nigdy nie importuje żadnego konkretnego
  rozszerzenia po nazwie. Zna wyłącznie protokół `NetworkExtension`
  (`extension_id`/`label`/`is_enabled`/`set_enabled`/`build_router()`),
  zdefiniowany w `network/extension_contract.py` — montuje router każdego
  rozszerzenia pod `/api/v1/extensions/{extension_id}` bez zaglądania do
  środka. Generyczny rejestr (`GET/PUT /api/v1/extensions*`) jest jedyną
  treścią współdzieloną między rozszerzeniami na tej granicy.
- Rozszerzenie samo orkiestruje swój backend wewnętrznie (dziś: `HomeAssistantExtension`
  → `HomeAssistantClient`, bez ABC ani dynamicznej rejestracji typów — Home
  Assistant jest jedynym, znanym z góry backendem tego rozszerzenia), włącznie
  z rozwiązywaniem grup urządzeń (patrz sekcja 3.4).

Dzięki temu Regis pozostaje **ogólnym agentem**, a Home Assistant jest tylko
*narzędziem, którego agent może użyć* — nie integralną częścią tego, czym
agent jest. Jeden identyfikator (`plugin_id == extension_id`, np.
`"home_assistant"`) obowiązuje na obu granicach jednocześnie plus opcjonalnie
na trzeciej: kluczu rejestru widoków frontendu (`EXTENSION_DETAIL_VIEWS`
w `web/js/views/extensions.js`).

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
  - **`routes/extensions.py`**: Generyczny rejestr rozszerzeń (`GET /api/v1/extensions`, `PUT /api/v1/extensions/{id}`) — lista i przełącznik enabled, wspólne dla wszystkich rozszerzeń. Prywatne endpointy per rozszerzenie (np. `extensions/home_assistant/routes.py` z `/api/v1/extensions/home_assistant/connections*`, `/groups*`) montowane są osobno przez `network/gateway.py`, nie stąd.
- **Gateway (`gateway.py`)**: Serwuje wbudowaną konsolę WWW (SPA), rejestruje centralny router API v1 (`create_api_router`) oraz generyczny rejestr rozszerzeń (`create_extensions_registry_router`, `GET/PUT /api/v1/extensions*`) — po jednym montuje router każdego rozszerzenia z listy `extensions: list[NetworkExtension]` pod `/api/v1/extensions/{extension_id}`, bez importowania żadnego z nich po nazwie. W modelu pojedynczej usługi strumieniowanie tokenów do konsoli realizowane jest przez protokół **SSE**. Dwukierunkowa bramka **WebSockets** (`ws://127.0.0.1:8000/ws`) jest wyłącznie **zaplanowana** jako punkt komunikacji w architekturze rozproszonej z wieloma usługami satelitarnymi — `gateway.py` nie rejestruje dziś żadnego endpointu WS.
- **`extension_contract.py`**: `NetworkExtension` (`typing.Protocol`) — jedyna wiedza sieci o istnieniu rozszerzeń, analogicznie do `PluginProvider` po stronie kernela. Rozszerzenie implementuje go strukturalnie (bez jawnego dziedziczenia), dostarczając `extension_id`, `label`, `is_enabled()`/`set_enabled()` i `build_router()`.
- **Kompozycja aplikacji**: Instancja FastAPI powstaje w `create_gateway_app()`, wołanym z asynchronicznej funkcji `main()` po inicjalizacji rejestru backendów, `PromptStore` i rozszerzeń. Moduł `server.main` **nie eksportuje** modułowego obiektu `app`, więc uruchomienie przez `uvicorn server.main:app --reload` nie jest możliwe (patrz `docs/onboarding.md`, sekcja 4).

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

### 3.4 Warstwa 1 — Rozszerzenia (`services/server/src/server/extensions`)
Jedna, samodzielna warstwa (dawny podział na Pluginy + Integracje scalony —
patrz "Świadome decyzje projektowe" niżej). Każde rozszerzenie: (a) spełnia
strukturalnie `PluginProvider` (widoczne dla Gateway), (b) opcjonalnie
spełnia `NetworkExtension` (widoczne dla sieci), (c) opcjonalnie ma własny
widok we frontendzie, rejestrowany jawnie po `extension_id` w
`web/js/views/extensions.js`.

- **`HomeAssistantExtension` (`home_assistant/extension.py`)**: Jedyny byt widoczny dla `Gateway`/sieci w tej domenie. `plugin_id == extension_id == "home_assistant"`. Sam orkiestruje Home Assistant wewnętrznie — bez ABC ani dynamicznej rejestracji typu integracji (Home Assistant jest jedynym, znanym z góry backendem). Wielość **instancji** (kilka jednoczesnych połączeń HA, np. „HA — parter” + „HA — piętro”) zostaje — to inna oś niż usunięty polimorfizm typu. Zarządza połączeniami, grupami urządzeń i deklaracjami widoczności katalogu jako plikami JSON (`data/extensions/home_assistant/{connections,groups,declarations}/*.json`) oraz przełącznikiem `state.json`. `build()` w pełni rozwiązuje grupy wewnętrznie, filtruje przez deklarację i zwraca Gateway już spłaszczoną listę encji (`EntitySpec`), w której grupa jest nieodróżnialna z zewnątrz od pojedynczego urządzenia.
- **Deklaracje widoczności katalogu**: `DeviceDeclarationEntry` (`enabled`, `display_name`) per natywny ID urządzenia, plik `declarations/{connection_id}.json`. Brak pliku (świeże połączenie) = wszystko widoczne — zgodność z zachowaniem sprzed tej warstwy. Pierwszy zapis z zakładki „Rozszerzenia” tworzy plik. Logika merge (`HomeAssistantExtension.resolve_devices()`) jest współdzielona między `build()` i endpointem katalogu (`GET/PUT .../catalog`) — zero duplikacji.
- **`Device` / `DeviceGroup` (`home_assistant/models.py`)**: Domenowy słownik rozszerzenia — konkretna realizacja generycznego `EntitySpec` z Kontraktu, pojęcie należące wyłącznie do niego. `Device.area` jest luźnym, opcjonalnym tagiem bez rejestru (świadomie **nie** ma rdzennego pojęcia "pokoju" — patrz sekcja 5).
- **`DeviceRegistry` (`home_assistant/registry.py`)**: Czysty magazyn urządzeń i grup na czas jednej interakcji (`get_device()`/`get_group()` po wewnętrznym ref) — **nie ma logiki dopasowania po nazwie**, agent adresuje encje wyłącznie przez opaque `entity_id` nadany przez Gateway.
- **Narzędzia LLM (`home_assistant/tools.py`)**: `get_state`, `turn_on`, `turn_off` — zaimplementowane **raz**, współdzielone przez wszystkie połączenia, adresowane przez parametr `entity_id`. Działają zarówno na pojedynczym urządzeniu, jak i na całej grupie (z agregacją częściowych niepowodzeń, `HomeAssistantToolExecutor._invoke_group`). Opisy narzędzi mogą jawnie wspominać „Home Assistant” jako etykietę źródła — nigdy natywny ID, `base_url` ani token.
- **`HomeAssistantClient` (`home_assistant/client.py`)**: Cała wiedza o formacie danych Home Assistant (`entity_id`, `domain.service`, atrybuty encji) zamknięta w tej klasie — plain class, bez ABC.
- **`BasicToolsExtension` (`basic_tools/extension.py`)**: Minimalne rozszerzenie dowodzące zasady symetrii Fakt↔narzędzie (wizja, sekcja 4.5) — jedno narzędzie (`get_time`) i jeden odpowiadający mu Fakt (`aktualna_data_i_godzina`), oba liczone z tego samego `datetime.now()` w jednym wywołaniu `build()`. Nie dostarcza żadnych encji. `build_router()` zwraca pusty `APIRouter` — enable/disable obsługuje w pełni generyczny rejestr rozszerzeń, brak potrzeby własnych endpointów.
- **`_shared/state.py`**: `ExtensionStateFileContent` (`enabled: bool = True`) — jeden mały model `state.json`, współdzielony przez oba rozszerzenia (DRY, nie kontrakt międzywarstwowy).

### 3.5 Warstwa Wspólna (`packages/shared/src/shared`)
- **`ConfigStore` (`config.py`)**: Centralny zarządca persystentnej konfiguracji w formacie JSON z automatyczną walidacją i domyślnymi wartościami.
- **`EventBus` (`event_bus.py`)**: Asynchroniczna magistrala zdarzeń pub/sub (`subscribe`/`publish`). **W pełni wpięta w przepływ strumieniowania** — `AgentEngine` publikuje zdarzenia `ServerEventType.CHAT_CHUNK/DONE/ERROR/CANCELLED`, a `interact_stream` subskrybuje je i tłumaczy z powrotem na strumień tokenów dla wywołującego. Dzięki temu rdzeń nie zna bezpośrednio odbiorców (SSE dziś, WebSockets satelitów w przyszłości).
- **`contracts.py`**: Definicje obiektów transferu danych (DTO) współdzielonych przez serwer i konsolę WWW:
  - **System**: `HealthResponse`.
  - **Dostawcy LLM**: `LLMProviderDTO`, `LLMProviderListResponse`, `SelectLLMProviderRequest`, `CreateLLMProviderRequest` oraz generyczna specyfikacja opcji (`ProviderOptionSpec`, `ProviderTypeSpecDTO`, `ProviderMetadataResponse`) — schema-driven forma uzasadniona realną wymiennością backendu LLM (Ollama/OpenRouter).
  - **Czat i sesje**: `ChatMessageDTO`, `SendChatMessageRequest`, `ChatResponseDTO`, `ChatSessionSummaryDTO`, `ChatSessionHistoryResponse`, `ChatSessionListResponse`, `CancelChatApiRequest`.
  - **Prompty systemowe**: `PromptDTO`, `PromptListResponse`, `CreatePromptRequest`, `UpdatePromptRequest`.
  - **Rejestr rozszerzeń**: `ExtensionSummaryDTO`, `ExtensionListResponse`, `SetExtensionEnabledRequest` — generyczny kształt „lista rozszerzeń", jedyna treść współdzielona między nimi. Prywatne słownictwo Home Assistant (połączenia, katalog, grupy) żyje lokalnie w `extensions/home_assistant/dto.py`, nie tutaj — nie ma już realnej wymienności backendu uzasadniającej schema-driven DTO na tej ścieżce (patrz "Świadome decyzje projektowe").
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
AgentEngine       Gateway         HomeAssistantExtension (build)   HomeAssistantClient (invoke)
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
2. **Dodawanie nowego rozszerzenia**: Nowy pakiet w `extensions/` z klasą, która spełnia strukturalnie `PluginProvider` (pole `plugin_id`, metoda `async def build(facts) -> PluginContribution`), wpięta do `Gateway(plugins=[...])` w `main.py`. Fakty nie mają osobnej kategorii — rozszerzenie, które chce proaktywnie dostarczyć kontekst, dopisuje `facts` do zwracanego `PluginContribution` obok narzędzi i encji, pamiętając o bliźniaczym narzędziu (wizja, sekcja 4.5). Jeśli rozszerzenie potrzebuje własnej konfiguracji przez REST (CRUD, przełącznik enabled), dodatkowo implementuje strukturalnie `NetworkExtension` (`extension_id`, `label`, `is_enabled`/`set_enabled`, `build_router()` z ROZSZERZENIA na własnych, względnych ścieżkach) i jest dopisane do `extensions=[...]` w `create_gateway_app(...)`. Jeśli nie potrzebuje własnych endpointów (jak `BasicToolsExtension`), `build_router()` po prostu zwraca pusty `APIRouter()` — enable/disable i tak obsługuje generyczny rejestr. Opcjonalny widok frontendowy: nowy plik w `web/js/views/extensions/`, dopisany do `EXTENSION_DETAIL_VIEWS` w `web/js/views/extensions.js` pod tym samym `extension_id`. **Żadna z tych operacji nie wymaga zmiany kernela, sieci ani istniejących rozszerzeń.**
3. **Model dystrybucji**: Nic ponad kernel nie jest architektonicznie uprzywilejowane — podział na "wbudowane" i "pobieralne" byłby decyzją dystrybucyjną, nie granicą kodu. Obecnie wszystko żyje w jednym pakiecie z jawną rejestracją w `main.py`; dynamiczne ładowanie pluginów, manifesty i sandboxing są **świadomie odłożone** (brak realnego przypadku użycia — YAGNI). Granica `PluginProvider` sprawia, że dodanie loadera w przyszłości nie wymaga przepisywania kernela.

### Świadome decyzje projektowe (nie zmieniać bez ponownej analizy)

- **Brak rdzennego pojęcia "pokoju" (`Room`)**: Narzucałoby kernelowi/pluginowi założenie „świat = dom z pokojami”, podczas gdy smart home jest tylko jedną z możliwych domen agenta. `Device.area` pozostaje luźnym tagiem bez rejestru. Świadomość przestrzenna będzie własnością przyszłego pluginu obecności/lokalizacji, deklarującego swoją pozycję jako Fakt (wizja, sekcja 4.3), a skorelowanie jej z urządzeniami należy do LLM, nie do sztywnej logiki serwera.
- **`DeviceGroup` należy do rozszerzenia, nie do kernela**: Model grupowania jest ściśle związany z `invoke`/capability tej konkretnej domeny i może przecinać granice połączeń tego samego rozszerzenia; generalizacja na poziom Gateway byłaby odtworzeniem kompozytora, którego architektura świadomie unika (wizja, sekcja 4.4 i 8).
- **Usunięcie polimorfizmu Plugin/Integration (`DeviceIntegration` ABC, dynamiczna rejestracja typów)**: Wcześniejszy podział `plugins/smart_home/` + `integrations/home_assistant.py` z `register_integration_type`/`TYPE_NAME`/`SCHEMA` przygotowywał grunt pod wymienność backendu smart home. W praktyce nigdy nie pojawił się drugi, realny kandydat obok Home Assistant — HA sam jest hubem agregującym inne ekosystemy (Zigbee, Z-Wave, Matter itd.), więc scenariusz, który miał uzasadniać ten polimorfizm, jest już rozwiązany na poziomie samego Home Assistant. Projekt jest prywatnym, jednoosobowym repo bez potrzeby hot-swapu backendu bez redeployu. Scalenie do jednej warstwy `extensions/home_assistant/` (klasa, żadnej ABC, konstruktor zamiast fabryki) usuwa realny koszt (dodatkowa warstwa pośrednia, schema-driven formularz) bez utraty jakiejkolwiek dzisiejszej funkcjonalności — wielość **instancji** (kilka połączeń HA naraz) zostaje, bo to inna, wciąż potrzebna oś. Jeśli kiedyś pojawi się drugi, realny backend smart home — wróć do tej decyzji z konkretnym przypadkiem użycia w ręku, nie z wyprzedzeniem.
- **Adresowanie po opaque ID, nie po nazwie**: Dawne dopasowywanie po przyjaznej nazwie (`DeviceRegistry.resolve()`) było kruche (niejednoznaczności, literówki) i zdradzało połączenie stojące za urządzeniem, gdy nazwa trafiała do logów/promptu. Gateway nadaje deterministyczny, nieprzezroczysty `entity_id` — stabilny w historii rozmowy mimo budowania kontekstu od zera co turę (wizja, sekcja 4.2).
- **Brak potwierdzeń dla akcji z efektami ubocznymi**: Narzędzia wykonują się automatycznie w pętli ReAct.
- **Zapis decyzji: ta sekcja zamiast osobnych ADR-ów**: Uzasadnienia mieszkają tam, gdzie i tak czyta się architekturę. Osobny katalog `docs/adr/` duplikowałby te treści i rozjeżdżał się z manifestem — w projekcie jednoosobowym to koszt bez odbiorcy. Zmieniasz jedną z powyższych decyzji? Zaktualizuj wpis, nie dopisuj nowego dokumentu obok.

### Zaplanowane, jeszcze niezaimplementowane

1. **Widoczność wywołań narzędzi w UI**: `EventBus` jest gotowy na rozszerzenie o `TOOL_CALL_START/RESULT`; obecnie wywołania trafiają wyłącznie do logów.
2. **Pamięć Długoterminowa i Wektorowa**: Planowana integracja modułów pamięci wektorowej i semantycznej w usłudze `server`.
3. **Skalowanie Usług Rozproszonych & WebSockets**: Przygotowanie infrastruktury `services/` pod uruchamianie dedykowanych mikrousług specjalistycznych (satelitów) w sieci lokalnej i ich komunikacji via WebSockets.
