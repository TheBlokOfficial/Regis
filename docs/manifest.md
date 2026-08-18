# Manifest Architektoniczny Systemu Regis

## 1. Wizja i Cel Systemu Regis

**System Regis** to modularna platforma usług rozproszonych komunikujących się w sieci lokalnej, przeznaczona do orkiestracji i wykonywania zadań przez inteligentnych agentów AI.

Kluczowe założenia architektoniczne Systemu Regis:
- **Lokalność i Rozproszenie**: Usługi działają wydajnie w sieci lokalnej z pełną kontrolą nad prywatnością danych i przepływem informacji. *(Dziś: jedna usługa `services/server`; wielousługowość to kierunek, nie stan obecny — patrz sekcja 5.)*
- **Hybrydowość modeli LLM**: Przezroczysta obsługa lokalnych modeli językowych (np. Ollama) oraz modeli chmurowych (np. OpenRouter).
- **Ogólny agent, jeden konkretny silnik świata**: Rdzeń (kernel) nie zna żadnej konkretnej domeny — zna wyłącznie minimalny protokół `WorldInterface`. Jedyny, konkretny silnik (`WorldEngine`, dziś: Home Assistant + rejestr satelit + `get_time`) jest wstrzykiwany w kompozycji aplikacji (`main.py`), analogicznie do dostawcy LLM.
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
│   └── server/       # Główna usługa serwera Regis (bramka REST/SSE, kernel, silnik świata, Web UI)
├── pyproject.toml    # Główna konfiguracja workspace, grupy dev (pytest, anyio) oraz pytest
└── README.md         # Wprowadzenie do projektu
```

### Struktura wewnętrzna usługi `services/server/src/server/`:

```text
server/
├── agent/          # KERNEL — "umysł" agenta, ogólny i domenowo-pusty
│   ├── engine.py            # AgentEngine: pętla ReAct, sesje
│   ├── context_provider.py  # WorldInterface (Protocol) + ContextBuild + NullWorldInterface — jedyna wiedza kernela o świecie zewnętrznym
│   ├── backend/      # Dostawcy LLM + typy narzędzi (ToolDefinition/ToolCallRequest/ToolResult)
│   ├── context/      # ContextBuilder
│   ├── memory/       # MemoryManager
│   └── prompts/      # PromptStore
├── world/          # Jedyny, konkretny silnik świata — implementuje WorldInterface
│   ├── engine.py     # WorldEngine — build(), CRUD configu/grup/deklaracji/satelit
│   ├── client.py     # HomeAssistantClient
│   ├── models.py     # Device, DeviceGroup, HomeAssistantConfig, SatelliteRegistration
│   ├── registry.py   # DeviceRegistry
│   ├── tools.py      # HomeAssistantToolExecutor, build_tool_definitions
│   └── routes.py     # REST konfiguracji (montowany wprost przez network/gateway.py)
├── network/        # Bramka FastAPI i routery REST/SSE
├── web/            # Wbudowana konsola SPA (HTML/CSS/JS)
├── config.py       # Settings (ConfigStore)
├── events.py       # ServerEventType
└── main.py         # Kompozycja aplikacji: wstrzykuje WorldEngine do AgentEngine i do sieci
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
|   KERNEL AGENTA (domenowo pusty)         |  |  WARSTWA WSPÓLNA        |
|  services/server/src/server/agent        |  |  packages/shared        |
|  - AgentEngine (pętla ReAct)             |  |  - EventBus             |
|  - MemoryManager (Session storage)       |  |  - ConfigStore          |
|  - ContextBuilder                        |  |  - Contracts (DTOs)     |
|  - WorldInterface (Protocol)             |  |  - Logging              |
+------------------------------------------+  +-------------------------+
        |                        |                        ^
        v                        v                        |
+------------------------+  +------------------------------------------+
| WARSTWA DOSTAWCÓW LLM  |  |  WORLDENGINE — jedyny silnik świata      |
| agent/backend          |  |  services/server/src/server/world        |
| - BackendRegistry      |  |  - HomeAssistantClient, Device,          |
| - BaseLLMProvider      |  |    DeviceGroup, rejestr satelit          |
|   (Ollama, OpenRouter) |  |  - woła własne backendy wprost, bez      |
+------------------------+  |    protokołu między nimi                 |
                             +------------------------------------------+
```

### Zasada kierunku zależności (fundament architektury)

**Kernel nie zna z góry konkretnej implementacji świata zewnętrznego — zna
wyłącznie *kształt* tego, co dostaje. `WorldEngine` wstrzykiwany jest jawnie
w kompozycji aplikacji (`main.py`), dokładnie jak konkretny dostawca LLM.**

- Kernel nigdy nie importuje niczego z `server/world/`. Zna wyłącznie
  protokół `WorldInterface` (`build(sender_id) -> ContextBuild`), zdefiniowany
  w `agent/context_provider.py`. `AgentEngine.world` domyślnie wskazuje na
  `NullWorldInterface` (pusty, bezpieczny stan — zwykły chat bez narzędzi),
  co pozwala wyjąć `agent/`+`memory/`+`context/`+`backend/`+`prompts/` do
  innej aplikacji bez ciągnięcia za sobą Home Assistant.
- `ContextBuild` niesie dwa ustrukturyzowane pola, których kernel **mechanicznie**
  potrzebuje (schemat API dostawcy LLM, wywołanie funkcji): `tool_definitions`
  i `dispatch`. Cała reszta treści promptu to jeden opaque blok prozy
  (`dynamic_context`) — jego kształt i formatowanie to wyłączna
  odpowiedzialność `WorldEngine`, kernel go tylko wkleja do system promptu.
- `WorldEngine` sam orkiestruje swoje wewnętrzne backendy (dziś:
  `HomeAssistantClient`, rejestr satelit) — zwykłymi wywołaniami metod, bez
  protokołu między nimi. To jeden, konkretny silnik, nie generyczna kolekcja
  wymiennych rozszerzeń — sieć (`network/gateway.py`) montuje jego router
  wprost, pod stałym prefiksem `/api/v1/world`, bez pośredniego protokołu
  ani generycznego rejestru enable/disable.

Dzięki temu Regis pozostaje **ogólnym agentem**, a Home Assistant jest tylko
*narzędziem, którego agent może użyć* — nie integralną częścią tego, czym
agent jest.

### Kolejność w `WorldEngine.build()` — kanał komunikacji niezależny od Home Assistant

`WorldEngine.build(sender_id)` czyta rejestrację satelity (kanał głos/tekst,
lokalizacja) **niezależnie** od dostępności/konfiguracji Home Assistant —
dopiero potem próbuje zbudować listę urządzeń, z tą samą łagodną degradacją
co dziś (brak `base_url`/`access_token` → po prostu brak narzędzi/encji HA,
bez wyjątku). Dzięki tej kolejności padnięcie/brak konfiguracji Home Assistant
ucina wyłącznie listę urządzeń, nigdy framing kanału komunikacji — a to
jedyny prawdziwy "wyłącznik" w tym silniku: nie ma osobnego booleana
`enabled`, backend albo działa, albo zwraca błąd w locie.

Urządzenia są **zawsze w pełni adresowalne** (żadne nie jest usuwane z
kontekstu) — kontekst przestrzenny to wyłącznie segregacja prezentacji:
`WorldEngine._render_devices_section` grupuje urządzenia po `Device.area`,
oznacza bieżący pokój nagłówkiem, ale nigdy nie chowa urządzeń z innych
pokoi ani nie blokuje na nich akcji.

### 3.1 Warstwa Sieciowa (`services/server/src/server/network`)
- **FastAPI Gateway (`gateway.py`) i zmodularyzowane routery (`routes/`)**: Obsługują punkty końcowe REST i SSE API v1 z podziałem na dedykowane pod-routery:
  - **`routes/health.py`**: Status zdrowia bramki i modułów (`GET /api/v1/health`).
  - **`routes/providers.py`**: Konfiguracja i zarządzenie dostawcami LLM (`GET/POST/PUT/DELETE /api/v1/llm/providers/*`, schemas).
  - **`routes/chat.py`**: Interakcje synchroniczne, strumieniowanie SSE i anulowanie (`POST /api/v1/chat/*`) — przekazuje opaque `sender_id` z `SendChatMessageRequest` do `AgentEngine`, bez interpretacji.
  - **`routes/sessions.py`**: Zarządzanie i historia sesji konwersacji (`GET/POST/DELETE /api/v1/chat/sessions/*`).
  - **`routes/prompts.py`**: CRUD promptów systemowych wraz z aktywacją (`GET/POST/PUT/DELETE /api/v1/agent/prompts/*`, `PUT /{id}/activate`).
- **`world/routes.py`**: Konfiguracja Home Assistant i satelit (`GET/PUT /api/v1/world/config`, `/catalog`, `/areas`, `/declared*`, `/groups*`, `/satellites*`) — montowany bezpośrednio przez `network/gateway.py` pod stałym prefiksem, opcjonalny (testy chat API mogą pominąć wstrzyknięcie `world_engine` i dostać czysty kernel bez tego routera).
- **Gateway (`gateway.py`)**: Serwuje wbudowaną konsolę WWW (SPA), rejestruje centralny router API v1 (`create_api_router`) oraz router `WorldEngine` pod `/api/v1/world`. W modelu pojedynczej usługi strumieniowanie tokenów do konsoli realizowane jest przez protokół **SSE**. Dwukierunkowa bramka **WebSockets** (`ws://127.0.0.1:8000/ws`) jest wyłącznie **zaplanowana** jako punkt komunikacji w architekturze rozproszonej z wieloma usługami satelitarnymi — `gateway.py` nie rejestruje dziś żadnego endpointu WS.
- **Kompozycja aplikacji**: Instancja FastAPI powstaje w `create_gateway_app()`, wołanym z asynchronicznej funkcji `main()` po inicjalizacji rejestru backendów, `PromptStore` i `WorldEngine`. Moduł `server.main` **nie eksportuje** modułowego obiektu `app`, więc uruchomienie przez `uvicorn server.main:app --reload` nie jest możliwe (patrz `docs/onboarding.md`, sekcja 4).

### 3.2 Kernel Agenta (`services/server/src/server/agent`)
- **`AgentEngine` (`engine.py`)**: Serce orkiestracji Systemu Regis. Realizuje **pełną pętlę agentyczną (ReAct)** — jeśli LLM zażąda wywołania narzędzia, wynik wraca do niego jako kolejna wiadomość i generacja jest kontynuowana, aż model zwróci odpowiedź finalną lub zostanie przekroczony `max_tool_iterations` (domyślnie 8). Kontroluje aktywne zadania konwersacyjne (`_active_tasks`), zarządza cyklem życia sesji oraz udostępnia metody `interact_stream` i `cancel_interaction`, wszystkie przyjmujące opaque `sender_id`. Na początku każdej interakcji woła `self.world.build(sender_id=sender_id)` (nigdy cache'owane) i przekazuje `tool_definitions`/`dynamic_context` do `ContextBuilder`.
- **`context_provider.py`**: `WorldInterface` (`typing.Protocol`, jedna metoda `build(sender_id) -> ContextBuild`), `ContextBuild` (`tool_definitions`/`dynamic_context`/`dispatch`) i `NullWorldInterface` — **jedyna wiedza kernela o istnieniu świata zewnętrznego**. Analogia: ta sama rola co `BaseLLMProvider` względem konkretnych dostawców LLM.
- **`MemoryManager` (`memory/session.py`)**: Odpowiada za utrwalanie historii rozmów per sesja na dysku (`data/sessions/*.json`). Do pamięci trafia **wyłącznie finalny tekst odpowiedzi** — pośrednie wiadomości `assistant`/`tool` z pętli ReAct żyją tylko w pamięci na czas jednej interakcji.
- **`ContextBuilder` (`context/builder.py`)**: Komponuje ostateczny prompt dla LLM, łącząc instrukcje systemowe z historią sesji. Przycina historię do `max_history_messages` najnowszych wiadomości (domyślnie 40, konfigurowalne w `settings.json`), by uniknąć przekroczenia limitu kontekstu modelu w długich konwersacjach. Przycinanie działa na podstawie liczby wiadomości, nie realnego zliczania tokenów. Parametr `tools_available` warunkowo dokleja jedno neutralne zdanie o dostępności narzędzi — nigdy nie wymienia ich nazw ani pochodzenia. Parametr `dynamic_context` (string z `ContextBuild`) jest wklejany wprost, bez żadnego formatowania po stronie kernela — kernel nie zna kształtu ani znaczenia jego treści.
- **`PromptStore` (`prompts/store.py`)**: Magazyn promptów systemowych (`data/prompts/*.json`) z wyborem aktywnego promptu (`data/active_prompt.json`). Usunięcie aktywnego promptu jest zablokowane; gdy nie da się wczytać żadnego, `ContextBuilder` używa `DEFAULT_SYSTEM_PROMPT` jako fallbacku — ten sam stały prompt zawiera też zdanie informujące agenta, że dynamiczny kontekst poniżej pochodzi z niezależnego silnika i nie należy zakładać w nim ukrytych zależności poza tym, co jawnie napisano.
  > **Pułapka**: `ensure_defaults()` tworzy domyślny prompt **tylko gdy katalog `data/prompts/` jest pusty**. Późniejsza zmiana `DEFAULT_SYSTEM_PROMPT` w kodzie **nie aktualizuje** już zapisanego pliku — treść, którą faktycznie dostaje LLM, żyje na dysku i zmienia się wyłącznie przez UI/REST.

### 3.3 Warstwa Dostawców LLM (`services/server/src/server/agent/backend`)
- **`BaseLLMProvider` (`providers/base.py`)**: Interfejs abstrakcyjny definiujący metodę `generate_stream(messages, tools)`, która yielduje `str` (fragment tekstu) **albo** `ToolCallRequest` (kompletne żądanie wywołania narzędzia). Cała złożoność formatu API konkretnego dostawcy (OpenRouter: akumulacja fragmentarycznych `delta.tool_calls` z SSE; Ollama: kompletne `tool_calls` w jednym komunikacie) jest ukryta wewnątrz providera — kernel operuje wyłącznie na abstrakcyjnych typach. Oba dostępne backendy wspierają tool calling.
- **`ToolDefinition` / `ToolCallRequest` / `ToolResult` (`providers/base.py`)**: Typy definiujące, **czym jest narzędzie** w całym systemie.
- **`BackendRegistry` (`registry.py`)**: Dynamiczny rejestr dostawców modeli z możliwością płynnego przełączania aktywnego backendu (np. z lokalnego `OllamaProvider` na chmurowy `OpenRouterProvider`).

### 3.4 WorldEngine (`services/server/src/server/world`)

Jedyny, konkretny silnik świata — implementuje `WorldInterface` strukturalnie
(bez importu z `agent/`). Wewnątrz: klient Home Assistant, rejestr satelit,
narzędzia — zwykłe, wprost wołane obiekty Pythona, zero protokołu między nimi.

- **`WorldEngine` (`engine.py`)**: Konfiguracja Home Assistant (singleton, jeden `base_url`/`access_token`), zadeklarowana lista urządzeń (opt-in), grupy i rejestr satelit — wszystko jako pliki JSON pod `data/world/` (`config.json`, `declared_devices.json`, `groups/*.json`, `satellites.json`). `build(sender_id)` czyta rejestrację satelity niezależnie od stanu Home Assistant (patrz sekcja 3 wyżej), segreguje urządzenia po `Device.area`, składa `dynamic_context` jako jeden string i zwraca `dispatch` wołający bezpośrednio `HomeAssistantToolExecutor`/logikę `get_time` po natywnym `entity_id` — **bez pośredniej warstwy opaque ID**: skoro istnieje dokładnie jeden silnik, nie ma ryzyka kolizji identyfikatorów między wieloma źródłami, więc nie ma po co ich ukrywać.
- **Katalog opt-in**: `DeclaredDeviceEntry` (tylko `display_name`) per natywny `entity_id`, plik `declared_devices.json`. Model jest **opt-in** — brak wpisu oznacza niewidoczność, niezależnie od tego, czy encja istnieje po stronie HA. `resolve_devices()` iteruje po zadeklarowanych wpisach i dociąga (join po `entity_id`) aktualny stan z surowego katalogu HA (`get_catalog()`).
- **`Device` / `DeviceGroup` / `SatelliteRegistration` (`models.py`)**: `Device.id` to wprost natywny `entity_id` Home Assistant (singleton — bez przestrzeni nazw połączenia). `Device.capabilities` to mapa nazwa narzędzia → granularne cechy (`dict[str, frozenset[str]]`). `Device.area` to natywny `area_id` Home Assistant — **jedyne** źródło pojęcia "pokój" w systemie, nadal nieobecne w kernelu (patrz sekcja 5). `SatelliteRegistration` (`room_key`/`room_label`/`channel`/`display_name`) mapuje opaque `sender_id` na pokój i kanał komunikacji — `room_key` musi zgadzać się z `Device.area`, co jest zależnością **konfiguracyjną** (administrator rejestrujący satelitę), nie kodową; `GET /api/v1/world/areas` (unikalne `area_id` wśród zadeklarowanych urządzeń) istnieje wyłącznie jako wygoda formularza rejestracji.
- **`DeviceRegistry` (`registry.py`)**: Czysty magazyn urządzeń i grup na czas jednej interakcji (`get_device()`/`get_group()` po natywnym `entity_id`).
- **Narzędzia LLM (`tools.py`)**: `get_state`, `turn_on`, `turn_off` — zaimplementowane **raz**, adresowane wprost przez natywny `entity_id`. Jasność/kolor/efekt świateł **nie są osobnymi narzędziami** — `light/turn_on` w Home Assistant przyjmuje je jako opcjonalne parametry tego samego wywołania (potwierdzone w `client.py`, `_call_service`), więc `turn_on` niesie opcjonalne pola `brightness_pct`/`color_temp_kelvin`/`rgb_color`/`effect` w jednym schemacie. Działają zarówno na pojedynczym urządzeniu, jak i na całej grupie (z agregacją częściowych niepowodzeń, `HomeAssistantToolExecutor._invoke_group`). `_validate_turn_on` sprawdza, że podano co najwyżej jedno z `color_temp_kelvin`/`rgb_color`, i że urządzenie deklaruje odpowiadającą cechę w `Device.capabilities["turn_on"]`.
- **`HomeAssistantClient` (`client.py`)**: Cała wiedza o formacie danych Home Assistant (`entity_id`, `domain.service`, atrybuty encji) zamknięta w tej klasie. Dekoduje capabilities per domena przez tabelę `_DOMAIN_DECODERS` — dziś tylko `"light"` ma bogaty dekoder (`_decode_light`, łączy `supported_color_modes` i bit `EFFECT` z `supported_features`, ufa wyłącznie `supported_color_modes` dla jasności/koloru); pozostałe domeny fallbackują na `_TOGGLEABLE_DOMAINS`/`get_state`-only.
- **`get_time`**: Narzędzie + odpowiadający fragment `dynamic_context` (aktualna data/godzina), liczone z tego samego `datetime.now()` w jednym wywołaniu `build()` — dowód zasady symetrii Fakt↔narzędzie (sekcja 5), dziś zaimplementowany bezpośrednio w `WorldEngine.build()`, nie jako osobny byt.

### 3.5 Warstwa Wspólna (`packages/shared/src/shared`)
- **`ConfigStore` (`config.py`)**: Centralny zarządca persystentnej konfiguracji w formacie JSON z automatyczną walidacją i domyślnymi wartościami.
- **`EventBus` (`event_bus.py`)**: Asynchroniczna magistrala zdarzeń pub/sub (`subscribe`/`publish`). **W pełni wpięta w przepływ strumieniowania** — `AgentEngine` publikuje zdarzenia `ServerEventType.CHAT_CHUNK/DONE/ERROR/CANCELLED` oraz `TOOL_CALL_START/TOOL_CALL_RESULT` (kroki pętli ReAct), a `interact_stream` subskrybuje je i tłumaczy z powrotem na strumień ustrukturyzowanych `StreamEvent` (`agent/engine.py`) dla wywołującego. Dzięki temu rdzeń nie zna bezpośrednio odbiorców (SSE dziś, WebSockets satelitów w przyszłości). `routes/chat.py` serializuje `StreamEvent` na ramki SSE z polem `type` (`chunk`/`tool_start`/`tool_result`). Ustrukturyzowany ślad kroków (`ToolStepPayload`: `call_id`/`name`/`text_offset`/`arguments`/`content`/`is_error`) trafia też — gdy tura użyła narzędzi — do `metadata.steps` finalnej wiadomości `assistant` w `MemoryManager`, więc Web UI potrafi odtworzyć całe drzewko ReAct (tekst/COT przeplecione z wywołaniami narzędzi) zarówno na żywo, jak i po powrocie do historii sesji.
- **`contracts.py`**: Definicje obiektów transferu danych (DTO) współdzielonych przez serwer i konsolę WWW:
  - **System**: `HealthResponse`.
  - **Dostawcy LLM**: `LLMProviderDTO`, `LLMProviderListResponse`, `SelectLLMProviderRequest`, `CreateLLMProviderRequest` oraz generyczna specyfikacja opcji (`ProviderOptionSpec`, `ProviderTypeSpecDTO`, `ProviderMetadataResponse`) — schema-driven forma uzasadniona realną wymiennością backendu LLM (Ollama/OpenRouter).
  - **Czat i sesje**: `ChatMessageDTO`, `SendChatMessageRequest` (w tym opaque `sender_id`), `ChatResponseDTO`, `ChatSessionSummaryDTO`, `ChatSessionHistoryResponse`, `ChatSessionListResponse`, `CancelChatApiRequest`.
  - **Prompty systemowe**: `PromptDTO`, `PromptListResponse`, `CreatePromptRequest`, `UpdatePromptRequest`.
  - Prywatne słownictwo Home Assistant/satelit (config, katalog, grupy, rejestracje) żyje lokalnie w `world/dto.py`, nie tutaj — nie ma potrzeby generycznego kształtu skoro istnieje dokładnie jeden silnik.
- **`logging.py`**: Jednolita konfiguracja logów dla całego monorepo z ustandaryzowanymi nazwami kategorii (`regis.main`, `regis.agent`, `regis.world`, itp.).

---

## 4. Przepływy Danych (Sequence Flow)

### 4.1 Przepływ Strumieniowej Interakcji (SSE - Server-Sent Events)
```text
Klient (Web UI)        FastAPI Gateway          AgentEngine        MemoryManager        LLM Provider        EventBus
       |                       |                     |                   |                   |                 |
       |-- POST /chat/stream ->|                     |                   |                   |                 |
       |                       |--- interact_stream ->|                   |                   |                 |
       |                       |                     |--- add_message -->|                   |                 |
       |                       |                     |--- world.build(sender_id) (od zera, co turę) |          |
       |                       |                     |--- build_messages (+dynamic_context) ->|                 |
       |                       |                     |--- generate_stream(tools) ----------->|                 |
       |                       |                     |--- publish CHAT_CHUNK ---------------------------------->|
       |<-- sse data chunk ----|<-- yield chunk -----|<-- (subskrypcja EventBus) ------------------------------|
       |                       |                     |--- add_assistant_msg -->|             |                 |
       |                       |                     |--- publish CHAT_DONE ----------------------------------->|
       |<-- sse data [DONE] ---|<--------------------|                   |                   |                 |
```

### 4.2 Pętla Agentyczna (ReAct — Tool Calling)
```text
AgentEngine       WorldEngine (build)              HomeAssistantClient (invoke)
     |                    |                                |
     |--- build(sender_id) -->|                             |
     |                    |--- list_devices() ------------>|
     |                    |<-- [Device] --------------------|
     |<-- tool_definitions, dynamic_context, dispatch ------|
     |                       |                        |
     |--- generate_stream(messages+dynamic_context, tools) ----------------->|
     |<-- ToolCallRequest("turn_on", {entity_id: "light.bathroom"}) ---------|
     |                       |                        |
     |--- dispatch("turn_on", {entity_id: "light.bathroom"}) -->|
     |                    |--- invoke(id, cap) -->|
     |<-- ToolResult -------------------------|<-- ToolResult ---------|
     |                       |                        |
     | [append assistant(tool_calls) + tool(result) do working_messages]   |
     |--- generate_stream(messages+wyniki, tools) --------------------------->|
     |<-- "Włączyłem światło." (tekst finalny) ---------------------------------|
     |                       |                        |
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
2. **Rozszerzanie możliwości agenta**: Skoro dziś istnieje dokładnie jeden, konkretny silnik świata, nowa możliwość (nowe narzędzie, nowy backend) jest po prostu dopisywana wewnątrz `server/world/` — zwykła metoda, zwykłe wywołanie. **Nie odtwarzaj generycznej wielorozszerzeniowości** (osobny pakiet + protokół + rejestr enable/disable) bez konkretnego, realnego drugiego silnika świata w ręku — patrz "Świadome decyzje projektowe" niżej. Jeśli taki przypadek się pojawi, granica `WorldInterface` sprawia, że wymiana `WorldEngine` na coś innego (albo wprowadzenie realnej wielości) nie wymaga przepisywania kernela.
3. **Model dystrybucji**: Nic ponad kernel nie jest architektonicznie uprzywilejowane — podział na "wbudowane" i "pobieralne" byłby decyzją dystrybucyjną, nie granicą kodu. Obecnie wszystko żyje w jednym pakiecie z jawną rejestracją w `main.py`; dynamiczne ładowanie pluginów, manifesty i sandboxing są **świadomie odłożone** (brak realnego przypadku użycia — YAGNI).

### Świadome decyzje projektowe (nie zmieniać bez ponownej analizy)

- **Usunięcie generycznej wielorozszerzeniowości (`PluginProvider`/`Gateway`/`NetworkExtension`, warstwa `extensions/`)**: Wcześniejszy model "N niezależnych, wzajemnie nieświadomych rozszerzeń" bronił się przed scenariuszem (podmiana/wielość konkurencyjnych silników świata), który w tym prywatnym, jednoosobowym projekcie nigdy się nie wydarzył — jedynym realnym konsumentem od początku był Home Assistant, a rozszerzanie o satelity/kanał komunikacji tylko to potwierdziło. Próba utrzymania wzajemnej nieświadomości między dwoma bytami mającymi dokładnie jednego wspólnego konsumenta (satelita→pokój, filtrowanie encji HA) generowała realny koszt bez korzyści: albo Fakty nadużyte jako kanał międzyrozszerzeniowy (łamanie ich pierwotnej roli — wyłącznie dla agenta), albo rówieśniczy DI między dwoma osobnymi rozszerzeniami (dwie pary protokołów, cykliczne wiązanie w `main.py`). Scalono do jednego, konkretnego `WorldEngine` (`server/world/`), wołającego swoje wewnętrzne backendy wprost. Analogiczna decyzja do wcześniejszego usunięcia `DeviceIntegration` ABC — ten sam wzorzec zastosowany o jeden poziom wyżej. **Jeśli kiedyś pojawi się drugi, realny, jednocześnie używany silnik świata (nie tylko drugi backend smart home, ale odrębna domena możliwości agenta) — wróć do tej decyzji z konkretnym przypadkiem w ręku, nie z wyprzedzeniem.**
- **Kanał komunikacji (głos/tekst) i lokalizacja satelity to wewnętrzna wiedza `WorldEngine`, nie osobny byt**: Rozważano osobne rozszerzenie "Presence" (z DI do Home Assistant przez `LocationProvider`/`AreaLookup`) specjalnie po to, żeby kanał komunikacji przetrwał brak/wyłączenie Home Assistant. Odrzucone — bo to mylące dwie różne osie niezależności. Prawdziwa oś to: świadome `is_enabled()==False` całego `WorldEngine` (jedyny wyłącznik) kontra chwilowa niedostępność/brak konfiguracji backendu HA (łagodna degradacja *wewnątrz* jednego `build()`). `WorldEngine.build()` liczy framing kanału/lokalizacji **przed** próbą kontaktu z Home Assistant, więc padnięcie/brak konfiguracji HA ucina tylko listę urządzeń, nigdy framing kanału — bez potrzeby osobnego bytu ani DI.
- **Filtrowanie zamienione na segregację prezentacji**: Rozważano dosłowne "pokaż tylko encje bieżącego pokoju" (z narzędziem awaryjnym do odsłaniania reszty) — odrzucone, bo opaque ID/adresowalność wymagałyby dodatkowej maszynerii (osobne pole "encje adresowalne, ale nierenderowane", eksport funkcji haszującej), a wieloetapowe wywołania narzędzi (`list_rooms`→`get_room`→akcja) zwiększają ryzyko błędu rozumowania u słabszych, lokalnych modeli (Ollama). `WorldEngine` zawsze zwraca wszystkie urządzenia w pełni adresowalne — kontekst przestrzenny to wyłącznie segregacja/nagłówki w `dynamic_context`.
- **Brak rdzennego pojęcia "pokoju" (`Room`) w kernelu**: Narzucałoby kernelowi założenie „świat = dom z pokojami”, podczas gdy smart home jest tylko jedną z możliwych domen agenta. `Device.area`/`SatelliteRegistration.room_key` pozostają wyłącznie wewnętrznym słownictwem `WorldEngine` — kernel go nie zna.
- **`DeviceGroup` należy do `WorldEngine`, nie do kernela**: Model grupowania jest ściśle związany z `invoke`/capability tej konkretnej domeny.
- **Usunięcie polimorfizmu Plugin/Integration (`DeviceIntegration` ABC, dynamiczna rejestracja typów)**: Wcześniejszy podział `plugins/smart_home/` + `integrations/home_assistant.py` z `register_integration_type`/`TYPE_NAME`/`SCHEMA` przygotowywał grunt pod wymienność backendu smart home. W praktyce nigdy nie pojawił się drugi, realny kandydat obok Home Assistant — HA sam jest hubem agregującym inne ekosystemy (Zigbee, Z-Wave, Matter itd.).
- **Home Assistant jako singleton, nie kolekcja połączeń**: Wcześniejszy model dopuszczał wiele nazwanych połączeń HA jednocześnie. W praktyce projekt jest jednoosobowy i prywatny z jedną instancją Home Assistant.
- **Katalog urządzeń opt-in, nie opt-out**: Nic nie jest widoczne, dopóki nie zostanie świadomie dodane przez wyszukiwarkę w UI — `declared_devices.json` jest listą *zawierającą*, jedynym źródłem prawdy o tym, co widzi agent.
- **Adresowanie po natywnym `entity_id`, nie po opaque ID ani po nazwie**: Dawne dopasowywanie po przyjaznej nazwie było kruche. Opaque ID istniało po to, żeby ukryć pochodzenie encji przy wielu, wzajemnie nieświadomych pluginach — skoro istnieje dokładnie jeden silnik świata, ryzyko kolizji/przecieku pochodzenia między pluginami nie istnieje, więc dodatkowa warstwa hashowania została świadomie porzucona (YAGNI). Do rewizji tylko z konkretnym powodem (np. potrzeba ukrycia wewnętrznego nazewnictwa HA przed LLM).
- **Brak potwierdzeń dla akcji z efektami ubocznymi**: Narzędzia wykonują się automatycznie w pętli ReAct.
- **Zapis decyzji: ta sekcja zamiast osobnych ADR-ów**: Uzasadnienia mieszkają tam, gdzie i tak czyta się architekturę. Zmieniasz jedną z powyższych decyzji? Zaktualizuj wpis, nie dopisuj nowego dokumentu obok.
- **Zasada symetrii Fakt↔narzędzie**: Każda informacja proaktywnie podana w `dynamic_context` musi być **również** dostępna reaktywnie, przez narzędzie zwracające dokładnie tę samą treść (dowód: `get_time` — narzędzie i fragment `dynamic_context` liczone z tego samego `datetime.now()` w jednym `build()`). Wyjątek: framing czysto instrukcyjny (np. "komunikujesz się głosem, pisz krótko") nie wymaga bliźniaczego narzędzia — nie jest wiedzą do odpytania na żądanie, tylko zawsze-obecną instrukcją.

### Zaplanowane, jeszcze niezaimplementowane

1. **Pamięć Długoterminowa i Wektorowa**: Planowana integracja modułów pamięci wektorowej i semantycznej w usłudze `server`.
2. **Skalowanie Usług Rozproszonych & WebSockets**: Przygotowanie infrastruktury `services/` pod uruchamianie dedykowanych mikrousług specjalistycznych (satelitów) w sieci lokalnej i ich komunikacji via WebSockets. Rejestr satelit (`WorldEngine`, `sender_id -> pokój/kanał`) już istnieje — Web UI jest dziś pierwszym, zawsze dostępnym "satelitą": generuje i trwale zapisuje własny opaque `sender_id` w `localStorage` (`web/js/sender_id.js`) i wysyła go z każdym `POST /api/v1/chat*`, a zakładka "Świat" pozwala zarejestrować tę przeglądarkę (albo dowolny inny `sender_id`) pod pokojem/kanałem. `sender_id` dziś przekazywany jest tylko przez HTTP (`SendChatMessageRequest.sender_id`), bez żadnego kanału WS — fizyczne satelity (ESP32) czekają na realne WebSockets.
3. **Widoczność kroków ReAct w toku generowania (polling fallback)**: `startPolling` (Web UI, fallback gdy SSE nie jest aktywne — np. po odświeżeniu strony w trakcie długiej pętli ReAct) pokazuje tylko narastający tekst finalnej odpowiedzi, bez kroków pośrednich — `metadata.steps` istnieje dopiero po zakończeniu tury.
4. **Zakładka ogólnej konfiguracji systemu**: Web UI ma dziś jeden, bezpośredni widok konfiguracji Home Assistant/satelit (`web/js/views/extensions.js` montuje `HomeAssistantExtensionView` wprost, bez generycznej listy). Szersza, ogólna zakładka konfiguracji systemu jest wizją końcową, nieporuszaną przez ten refaktor.
