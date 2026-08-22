# Manifest Architektoniczny Systemu Regis

## 1. Wizja i Cel Systemu Regis

**System Regis** to modularna platforma usług rozproszonych komunikujących się w sieci lokalnej, przeznaczona do orkiestracji i wykonywania zadań przez inteligentnych agentów AI.

Kluczowe założenia architektoniczne Systemu Regis:
- **Lokalność i Rozproszenie**: Usługi działają wydajnie w sieci lokalnej z pełną kontrolą nad prywatnością danych i przepływem informacji. *(Dziś: jedna usługa `services/server`; wielousługowość to kierunek, nie stan obecny — patrz sekcja 5.)*
- **Hybrydowość modeli LLM**: Przezroczysta obsługa lokalnych modeli językowych (np. Ollama) oraz modeli chmurowych (np. OpenRouter).
- **Ogólny agent, jeden konkretny silnik świata**: Rdzeń (kernel) nie zna żadnej konkretnej domeny — zna wyłącznie minimalny protokół `WorldInterface`. Jedyny, konkretny silnik (`WorldEngine`, dziś: Home Assistant + przypisania nadawców do pokoi + `get_time` + `speak_in_room`) jest wstrzykiwany w kompozycji aplikacji (`main.py`), analogicznie do dostawcy LLM.
- **Ogólny agent, rozłączny pipeline głosowy**: `server/voice/` (WS gateway satelit, wake-word/VAD-signaling, STT/TTS) jest **peerem** `WorldEngine`, nie jego częścią ani konsumentem — oba znają wyłącznie opaque `sender_id` przepływający przez kernel, nigdy się nawzajem nie importują. Patrz sekcja 3.6 i sekcja 5 ("Świadome decyzje projektowe").
- **Czas Rzeczywisty**: Strumieniowanie odpowiedzi w czasie rzeczywistym przez **SSE** oraz asynchroniczną magistralę zdarzeń (`EventBus`). Dwukierunkowe **WebSockets** działają dziś dla satelit głosowych (`WS /ws/voice/{sender_id}`, `server/voice/gateway.py`) — bez uwierzytelniania (świadome założenie, model zaufanej sieci lokalnej).
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
│   └── shared/       # Paczka shared (ConfigStore, EventBus, DTO, kontrakt WS voice_protocol, logging)
├── services/         # Niezależne usługi sieciowe
│   ├── server/       # Główna usługa serwera Regis (bramka REST/SSE, kernel, silnik świata, Web UI)
│   └── desktop_satellite/  # Klient WS satelity desktopowej (Windows/Linux) — mikrofon/głośnik
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
│   └── prompts/      # AgentDefaultPromptStore — jedna wartość, fallback bez CRUD (używany tylko gdy World milczy)
├── world/          # Jedyny, konkretny silnik świata — implementuje WorldInterface, JEDYNY autor promptu tury
│   ├── engine.py     # WorldEngine — build() (system_prompt = profil + fakty), CRUD configu/grup/pokoi/deklaracji/nadawców/profili promptu, speak_in_room
│   ├── prompts.py    # WorldPromptStore — CRUD do 3 przełączalnych profili tożsamości (data/world/prompts/*.json)
│   ├── client.py     # HomeAssistantClient
│   ├── models.py     # Device, DeviceGroup, Room, HomeAssistantConfig, SenderProfile
│   ├── registry.py   # DeviceRegistry
│   ├── tools.py      # HomeAssistantToolExecutor, build_tool_definitions
│   └── routes.py     # REST konfiguracji + CRUD profili promptu (montowany wprost przez network/gateway.py)
├── voice/          # Pipeline głosowy satelit — peer WorldEngine, rozłączny (patrz sekcja 3.6)
│   ├── gateway.py    # WS endpoint /voice/{sender_id}, VoiceConnection (handshake, ciągła subskrypcja EventBus), śledzenie connected_sender_ids
│   ├── session.py    # VoiceSession — automat stanu jednej rozmowy
│   ├── wakeword.py    # WakeWordDetector — OnnxWakeWordDetector (realny model .onnx) z fallbackiem do placeholdera
│   └── stt.py / tts.py # BaseSTTProvider/BaseTTSProvider (dziś: dev-providerzy Mock*)
├── network/        # Bramka FastAPI i routery REST/SSE
├── web/            # Wbudowana konsola SPA (HTML/CSS/JS)
├── config.py       # Settings (ConfigStore)
├── events.py       # ServerEventType
├── discovery.py    # DiscoveryBroadcaster — UDP broadcast obecności serwera (auto-discovery satelit)
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
|  - BaseLLMProvider (Protocol, llm.py)    |  |                         |
+------------------------------------------+  +-------------------------+
        |                        |                        ^
        v                        v                        |
+------------------------+  +------------------------------------------+
| KONKRETY AI            |  |  WORLDENGINE — jedyny silnik świata      |
| services/server/src/   |  |  services/server/src/server/world        |
|   server/ai            |  |  - HomeAssistantClient, Device,          |
| - ai/llm (BackendRegi- |  |    DeviceGroup, rejestr satelit          |
|   stry, Ollama, Open-  |  |  - woła własne backendy wprost, bez      |
|   Router)              |  |    protokołu między nimi                 |
| - ai/stt, ai/tts       |  +------------------------------------------+
|   (Groq, ElevenLabs)   |
+------------------------+
```

Sąsiad `agent/`/`world/`, budowany od zera 2026-08-21: trzyma wyłącznie
**konkretne** implementacje i logikę wyboru dostawcy AI (LLM/STT/TTS).
Protokoły (`BaseLLMProvider`, `BaseSTTProvider`, `BaseTTSProvider`) zostają
we właściwych domenach (`agent/llm.py`, `voice/stt.py`, `voice/tts.py`) —
dokładnie ten sam podział co `WorldInterface` (zostaje w `agent/`) vs
`WorldEngine` (konkretna implementacja, sąsiedni `world/`).

**Singleton-router per moduł (`LLMRouter`/`STTRouter`/`TTSRouter`)** — `agent/`
i `voice/` nie trzymają referencji do zamrożonego konkretu, tylko do
stabilnego routera należącego do `ai/*`, który implementuje odpowiedni
protokół i **przy każdym wywołaniu** sam rozwiązuje aktualnie aktywny konkret
(cache'owany, przebudowywany tylko gdy zmieni się aktywne ID/config — patrz
`ai/llm/router.py`, `ai/stt/router.py`, `ai/tts/router.py`). `main.py`
konstruuje router raz i wstrzykuje go dokładnie jak wcześniej wstrzykiwał
konkret (`self.llm_provider.generate_stream(...)`,
`self._stt_provider.transcribe(...)`, `self._tts_provider.synthesize(...)` —
bez zmian po stronie wywołującej). Dzięki temu zmiana aktywnego backendu LLM
(`PUT /api/v1/llm/providers/active`) i configu STT/TTS
(`PUT /api/v1/voice/providers/config`) działa **natychmiast, bez restartu
serwera** — REST-y już nie mutują `agent_engine`/`voice` z zewnątrz (wcześniej
`network/routes/providers.py` robił `agent_engine.llm_provider = ...`, co było
złamaniem hermetyzacji; STT/TTS nie miały tej mutacji wcale, stąd wymóg
restartu przed tą zmianą). `BaseSTTProvider`/`BaseTTSProvider` mają wspólną,
nieabstrakcyjną metodę `get_active_provider_class_name()` (domyślnie zwraca
własną klasę, `STTRouter`/`TTSRouter` nadpisują, zwracając nazwę rozwiązanego
konkretu) — używana przez `GET /api/v1/voice/status` do raportowania
Mock/real bez ujawniania szczegółów routingu.

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
  i `dispatch`. Trzecie pole, `system_prompt: str | None`, to **kompletny,
  gotowy prompt tej tury** — gdy World jest podłączony i ma coś do powiedzenia,
  jest jedynym autorem całej treści (sam dokleja swój aktywny profil tożsamości
  do dynamicznych faktów, patrz `world/prompts.py`), kernel niczego nie skleja
  ani nie formatuje. `None` oznacza brak wkładu World — kernel wtedy używa
  własnego, prostego fallbacku (`agent/prompts/`, `AgentDefaultPromptStore`,
  bez CRUD). Ten podział celowo unika sytuacji, w której dwaj niepowiązani
  autorzy (kernel + World) muszą nieformalnie respektować wspólną hierarchię
  formatowania (Markdown, nagłówki) przy sklejaniu dwóch fragmentów promptu —
  wcześniejszy model (`dynamic_context` doklejany do promptu wybranego w
  kernelu) miał dokładnie ten problem.
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
`WorldEngine._render_devices_section` grupuje urządzenia po `Device.room_id`
(pełnoprawny `Room` World, niezależny od Home Assistant Areas — sekcja 5),
oznacza bieżący pokój nagłówkiem, ale nigdy nie chowa urządzeń z innych
pokoi ani nie blokuje na nich akcji.

### 3.1 Warstwa Sieciowa (`services/server/src/server/network`)
- **FastAPI Gateway (`gateway.py`) i zmodularyzowane routery (`routes/`)**: Obsługują punkty końcowe REST i SSE API v1 z podziałem na dedykowane pod-routery:
  - **`routes/health.py`**: Status zdrowia bramki i modułów (`GET /api/v1/health`).
  - **`routes/providers.py`**: Konfiguracja i zarządzenie dostawcami LLM (`GET/POST/PUT/DELETE /api/v1/llm/providers/*`, schemas).
  - **`routes/chat.py`**: Interakcje synchroniczne, strumieniowanie SSE, "wyślij i zapomnij" i anulowanie (`POST /api/v1/chat/*`) — przekazuje opaque `sender_id` z `SendChatMessageRequest` do `AgentEngine`, bez interpretacji.
  - **`routes/sessions.py`**: Zarządzanie i historia sesji konwersacji (`GET/POST/DELETE /api/v1/chat/sessions/*`) oraz kanał obserwujący sesję w czasie rzeczywistym (`GET /api/v1/chat/sessions/{id}/watch`).
  - **`routes/prompts.py`**: Fallbackowy prompt systemowy kernela, jedno pole bez CRUD (`GET/PUT /api/v1/agent/prompt`) — używany tylko gdy World nie dostarcza własnego promptu.
- **`world/routes.py`**: Konfiguracja Home Assistant, pokoi, nadawców i profili promptu (`GET/PUT /api/v1/world/config`, `/catalog`, `/areas`, `/declared*`, `/groups*`, `/rooms*`, `/senders*`, `/prompts*`) — montowany bezpośrednio przez `network/gateway.py` pod stałym prefiksem, opcjonalny (testy chat API mogą pominąć wstrzyknięcie `world_engine` i dostać czysty kernel bez tego routera).
- **Gateway (`gateway.py`)**: Serwuje wbudowaną konsolę WWW (SPA, z middleware `Cache-Control: no-cache` dla `/js/`/`/css/` — SPA bez wersjonowanych nazw plików, bez tego przeglądarki potrafią heurystycznie cache'ować JS/CSS na długo po wdrożeniu zmian), rejestruje centralny router API v1 (`create_api_router`), router `WorldEngine` pod `/api/v1/world` oraz opcjonalnie router `server.voice` (`WS /ws/voice/{sender_id}` + `GET /api/v1/voice/status`, patrz sekcja 3.5). W modelu pojedynczej usługi strumieniowanie tokenów do konsoli realizowane jest przez protokół **SSE**; dwukierunkowe **WebSockets** działają dziś dla satelit głosowych.
- **Kompozycja aplikacji**: Instancja FastAPI powstaje w `create_gateway_app()`, wołanym z asynchronicznej funkcji `main()` po inicjalizacji rejestru backendów, fallbackowego `AgentDefaultPromptStore` i `WorldEngine` (który wewnętrznie zarządza własnym `WorldPromptStore`, bez wstrzykiwania z `main.py`). Moduł `server.main` **nie eksportuje** modułowego obiektu `app`, więc uruchomienie przez `uvicorn server.main:app --reload` nie jest możliwe (patrz `docs/onboarding.md`, sekcja 4).

### 3.2 Kernel Agenta (`services/server/src/server/agent`)
- **`AgentEngine` (`engine.py`)**: Serce orkiestracji Systemu Regis. Realizuje **pełną pętlę agentyczną (ReAct)** — jeśli LLM zażąda wywołania narzędzia, wynik wraca do niego jako kolejna wiadomość i generacja jest kontynuowana, aż model zwróci odpowiedź finalną lub zostanie przekroczony `max_tool_iterations` (domyślnie 8). Kontroluje aktywne zadania konwersacyjne (`_active_tasks`), zarządza cyklem życia sesji oraz udostępnia metody `interact_stream` i `cancel_interaction`, wszystkie przyjmujące opaque `sender_id`. Na początku każdej interakcji woła `self.world.build(sender_id=sender_id)` (nigdy cache'owane); jeśli `context_build.system_prompt is None` (World milczy), dociąga fallback z `self.prompt_store.get_content()` — w obu przypadkach do `ContextBuilder` trafia już gotowy, pojedynczy `system_prompt`.
- **`context_provider.py`**: `WorldInterface` (`typing.Protocol`, jedna metoda `build(sender_id) -> ContextBuild`), `ContextBuild` (`tool_definitions`/`system_prompt`/`dispatch`) i `NullWorldInterface` (`system_prompt=None`) — **jedyna wiedza kernela o istnieniu świata zewnętrznego**. Analogia: ta sama rola co `BaseLLMProvider` względem konkretnych dostawców LLM.
- **`MemoryManager` (`memory/session.py`)**: Odpowiada za utrwalanie historii rozmów per sesja na dysku (`data/sessions/*.json`). Do pamięci trafia **wyłącznie finalny tekst odpowiedzi** — pośrednie wiadomości `assistant`/`tool` z pętli ReAct żyją tylko w pamięci na czas jednej interakcji.
- **`ContextBuilder` (`context/builder.py`)**: Komponuje ostateczny prompt dla LLM, łącząc instrukcje systemowe z historią sesji. Przycina historię do `max_history_messages` najnowszych wiadomości (domyślnie 40, konfigurowalne w `settings.json`), by uniknąć przekroczenia limitu kontekstu modelu w długich konwersacjach. Przycinanie działa na podstawie liczby wiadomości, nie realnego zliczania tokenów. Parametr `tools_available` warunkowo dokleja jedno neutralne zdanie o dostępności narzędzi — nigdy nie wymienia ich nazw ani pochodzenia. Parametr `system_prompt` (już gotowy string — wkład World albo fallback kernela) jest wklejany wprost jako treść systemowa, bez żadnego dalszego sklejania czy formatowania po stronie kernela.
- **`AgentDefaultPromptStore` (`prompts/store.py`)**: Jedna wartość (`data/agent_default_prompt.json`), bez CRUD — fallback używany **wyłącznie** gdy `ContextBuild.system_prompt is None` (brak World albo `NullWorldInterface`, np. testy headless / przenośność kernela). Przy pierwszym uruchomieniu bez pliku próbuje best-effort migracji z dawnego legacy `data/prompts/*.json`+`active_prompt.json`; w przeciwnym razie zasiewa `DEFAULT_SYSTEM_PROMPT`. Właściwy, edytowalny CRUD tożsamości (do 3 przełączalnych profili) żyje dziś w `world/prompts.py` — World jest jedynym autorem promptu, gdy jest podłączony (patrz sekcja 3.4, sekcja 5).

### 3.3 Protokół LLM (`services/server/src/server/agent/llm.py`) i konkrety (`server/ai/llm`)
- **`BaseLLMProvider` (`agent/llm.py`)**: Interfejs abstrakcyjny definiujący metodę `generate_stream(messages, tools)`, która yielduje `str` (fragment tekstu) **albo** `ToolCallRequest` (kompletne żądanie wywołania narzędzia). Cała złożoność formatu API konkretnego dostawcy (OpenRouter: akumulacja fragmentarycznych `delta.tool_calls` z SSE; Ollama: kompletne `tool_calls` w jednym komunikacie) jest ukryta wewnątrz providera — kernel operuje wyłącznie na abstrakcyjnych typach. Zostaje w `agent/` (kernel jest jego właścicielem, tak jak `WorldInterface`), mimo że wszystkie konkretne backendy mieszkają w sąsiednim `server/ai/llm/` — patrz sekcja "Konkrety AI" wyżej.
- **`ToolDefinition` / `ToolCallRequest` / `ToolResult` (`agent/llm.py`)**: Typy definiujące, **czym jest narzędzie** w całym systemie.
- **`OllamaProvider` / `OpenAICompatibleProvider` (`ai/llm/providers/`)**: Konkretne implementacje `BaseLLMProvider`. Obie wspierają tool calling. `OpenAICompatibleProvider` (scalone 2026-08-21 — wcześniej dwie niemal identyczne klasy `OpenRouterProvider`/`GroqProvider`) obsługuje **dwa** `ProviderType` naraz: `OPENROUTER` i `GROQ` — to jeden konkret REST OpenAI-compatible, parametryzowany przez `base_url`/`extra_headers`/`extra_payload` (konstruowany różnie per typ w `LLMFactory.create_provider()`, patrz niżej). `ProviderType`/schemat/badge na karcie **zostają rozdzielone** mimo scalonej implementacji — to dwa różne konta/klucze API z perspektywy użytkownika, więc dropdown i identyfikacja instancji (`p.type`) muszą pozostać osobne; scalenie dotyczy wyłącznie kodu, nie UI. Endpoint Groq: `https://api.groq.com/openai/v1/chat/completions` (kontrakt zweryfikowany w dokumentacji Groq, nie zgadywany), format SSE/tool_calls identyczny jak OpenRouter. OpenRouter dokłada `extra_payload={"reasoning": {"effort": "none"}}` i `extra_headers={"HTTP-Referer": ..., "X-Title": ...}` — rozszerzenia specyficzne dla OpenRouter, nieudokumentowane w API Groq, więc Groq ich nie dostaje. `base_url` **nie** jest polem formularza dla OPENROUTER/GROQ (zaszyty na sztywno w fabryce) — w odróżnieniu od Ollamy, gdzie jest edytowalny (self-hosted, zmienny).
- **`LLMFactory` (`ai/llm/factory.py`)**: Tworzy instancję providera z `BackendInstanceConfig` (Single Source of Truth dla schematów opcji konfiguracyjnych, `get_all_schemas()`).
- **`BackendRegistry` (`ai/llm/registry.py`)**: Dynamiczny rejestr dostawców modeli (pliki JSON w `data/backends/`) z możliwością płynnego przełączania aktywnego backendu (np. z lokalnego `OllamaProvider` na chmurowy `OpenAICompatibleProvider` — OpenRouter albo Groq).

### 3.4 WorldEngine (`services/server/src/server/world`)

Jedyny, konkretny silnik świata — implementuje `WorldInterface` strukturalnie
(bez importu z `agent/`). Wewnątrz: klient Home Assistant, rejestr satelit,
narzędzia — zwykłe, wprost wołane obiekty Pythona, zero protokołu między nimi.

- **`WorldEngine` (`engine.py`)**: Konfiguracja Home Assistant (singleton, jeden `base_url`/`access_token`), zadeklarowana lista urządzeń (opt-in), grupy, pokoje, przypisania nadawców do pokoi i profile promptu — wszystko jako pliki JSON pod `data/world/` (`config.json`, `declared_devices.json`, `groups/*.json`, `rooms/*.json`, `senders.json`, `prompts/*.json`+`active_prompt.json`). `build(sender_id)` pobiera treść aktywnego profilu promptu (`WorldPromptStore.get_active_content()`, może być pusty string — brak persony), doklejają ją PRZED faktami (przypisanie nadawcy niezależnie od stanu Home Assistant, patrz sekcja 3 wyżej; urządzenia posegregowane po `Device.room_id`), i składa całość jako jeden `system_prompt` string — **World jest jedynym autorem tej tury**, kernel niczego nie skleja. Zwraca też `dispatch` wołający bezpośrednio `HomeAssistantToolExecutor`/logikę `get_time`/`speak_in_room` po natywnym `entity_id` — **bez pośredniej warstwy opaque ID**: skoro istnieje dokładnie jeden silnik, nie ma ryzyka kolizji identyfikatorów między wieloma źródłami, więc nie ma po co ich ukrywać. `build(sender_id)` wyprowadza ramowanie dostawy z `SenderProfile.capabilities` (`ClientCapability.MIC/SPEAKER/TEXT`) — obecność `SPEAKER` decyduje, czy prompt mówi "odpowiedź zostanie odczytana na głos" czy "zostanie wyświetlona jako tekst" (`_render_delivery_framing`, wspólne dla `build()` i wyniku `speak_in_room`). Zastąpiło to dawny parametr `voice_mode: bool` — patrz sekcja 5, "Modalność to capability klienta".
- **`WorldPromptStore` (`prompts.py`)**: CRUD do **3** przełączalnych profili tożsamości (`list_all`/`get`/`create`/`update`/`delete`/`set_active`/`get_active_content`) — dosłownie dawny, wieloprofilowy `PromptStore` z `agent/prompts/`, przeniesiony do World razem z odpowiedzialnością za tożsamość agenta. `create()` rzuca `ValueError` przy próbie utworzenia 4. profilu. Domyślnie zawsze istnieje **"Profil 1"** z pustą treścią (World nie dziedziczy tożsamości po kernelu) — pusty aktywny profil oznacza "brak persony, tylko dynamiczne fakty", nie błąd.
- **Katalog opt-in**: `DeclaredDeviceEntry` (`display_name`, `room_id`) per natywny `entity_id`, plik `declared_devices.json`. Model jest **opt-in** — brak wpisu oznacza niewidoczność, niezależnie od tego, czy encja istnieje po stronie HA. `resolve_devices()` iteruje po zadeklarowanych wpisach i dociąga (join po `entity_id`) aktualny stan z surowego katalogu HA (`get_catalog()`), kopiując `room_id` z deklaracji na budowany `Device`.
- **`Room` (`models.py`) — pełnoprawny byt World, niezależny od Home Assistant Areas**: `{id, name}`, CRUD (`create_room`/`list_rooms`/`update_room`/`delete_room`) będący dokładnym mirrorem `DeviceGroup`. `Device.area` (surowy `area_id` HA) pozostaje wyłącznie **podpowiedzią** w surowym katalogu (`GET /world/catalog`) — nigdy prawdą o pokoju; `WorldEngine.import_rooms_from_ha()` to jawna, **jednorazowa** akcja tworząca `Room` per unikalna, niepusta HA Area jeszcze nieobecna wśród istniejących pokoi (dopasowanie po nazwie, bez rozróżniania wielkości liter) — nie ciągła synchronizacja. Uzasadnienie pełne w sekcji 5.
- **`Device` / `DeviceGroup` / `SenderProfile` (`models.py`)**: `Device.id` to wprost natywny `entity_id` Home Assistant (singleton — bez przestrzeni nazw połączenia). `Device.capabilities` to mapa nazwa narzędzia → granularne cechy (`dict[str, frozenset[str]]`). `Device.room_id` (kopiowane z `DeclaredDeviceEntry.room_id`) to **jedyne** źródło pojęcia "pokój" w systemie, nadal nieobecne w kernelu (patrz sekcja 5). `SenderProfile` (wyłącznie `room_id`, **bez** kanału komunikacji ani tożsamości urządzenia — to wiedza `server/voice`, patrz sekcja 3.5) mapuje opaque `sender_id` na `Room` — zgodność `room_id` z rzeczywistym rozmieszczeniem satelity jest odpowiedzialnością **konfiguracyjną** (administrator rejestrujący nadawcę), nie kodową.
- **`DeviceRegistry` (`registry.py`)**: Czysty magazyn urządzeń i grup na czas jednej interakcji (`get_device()`/`get_group()` po natywnym `entity_id`).
- **Narzędzia LLM (`tools.py`)**: `get_state`, `turn_on`, `turn_off` — zaimplementowane **raz**, adresowane wprost przez natywny `entity_id`. Jasność/kolor/efekt świateł **nie są osobnymi narzędziami** — `light/turn_on` w Home Assistant przyjmuje je jako opcjonalne parametry tego samego wywołania (potwierdzone w `client.py`, `_call_service`), więc `turn_on` niesie opcjonalne pola `brightness_pct`/`color_temp_kelvin`/`rgb_color`/`effect` w jednym schemacie. `_validate_turn_on` sprawdza, że podano co najwyżej jedno z `color_temp_kelvin`/`rgb_color`, i że urządzenie deklaruje odpowiadającą cechę w `Device.capabilities["turn_on"]`.

  **`entity_id` przyjmuje string albo tablicę stringów** (dodane 2026-08-21, powód: modele bez wsparcia dla równoległych tool calls — np. udokumentowane `openai/gpt-oss-120b` na Groq, `Parallel Tool Use Support: No` — musiały wykonać N osobnych rund pętli ReAct dla N urządzeń, kosztowne w tokenach i podatne na rate limit dostawcy). `HomeAssistantToolExecutor.execute()` to dziś **jedna** ścieżka zamiast dawnego rozgałęzienia urządzenie/grupa: normalizuje `entity_id` do listy, rozwiązuje każdą referencję jako urządzenie **albo** grupę (grupa rozwija się do swoich urządzeń — może więc być jednym z elementów tablicy, nie jedynym argumentem), po czym dla dokładnie jednego rozwiązanego urządzenia bez błędów zwraca surowy komunikat klienta wprost (zachowuje dzisiejsze proste "Pomyślnie wyłączono urządzenie."), a dla wielu — zagregowane podsumowanie sukces/porażka (dawna logika `_invoke_group`, uogólniona, bez założenia że źródłem musi być zapisana grupa). Grupy (`DeviceGroup`) zostają jako wygodny skrót dla stałych, nazwanych zestawów — nie są już jedynym sposobem adresowania wielu urządzeń naraz.
- **`HomeAssistantClient` (`client.py`)**: Cała wiedza o formacie danych Home Assistant (`entity_id`, `domain.service`, atrybuty encji) zamknięta w tej klasie. Dekoduje capabilities per domena przez tabelę `_DOMAIN_DECODERS` — dziś tylko `"light"` ma bogaty dekoder (`_decode_light`, łączy `supported_color_modes` i bit `EFFECT` z `supported_features`, ufa wyłącznie `supported_color_modes` dla jasności/koloru); pozostałe domeny fallbackują na `_TOGGLEABLE_DOMAINS`/`get_state`-only.
- **`get_time`**: Narzędzie + odpowiadający fragment `system_prompt` (aktualna data/godzina), liczone z tego samego `datetime.now()` w jednym wywołaniu `build()` — dowód zasady symetrii Fakt↔narzędzie (sekcja 5), dziś zaimplementowany bezpośrednio w `WorldEngine.build()`, nie jako osobny byt.
- **`speak_in_room`**: Narzędzie przekierowujące dostawę *dalszej części* bieżącej odpowiedzi do nadawcy przypisanego do innego pokoju (np. "powiedz to w kuchni"). Parametr widoczny dla LLM to wyłącznie **pokój** — ten sam słownik co nagłówki `### Kuchnia` w `system_prompt` — `sender_id` nigdy nie wycieka do promptu (dowód zasady "adresowanie po natywnym ID/etykiecie, nie po opaque ID", sekcja 5, zastosowanej też do nadawców, nie tylko urządzeń). Rezolucja (`WorldEngine._find_speaker_by_room`) to dwa kroki: nazwa pokoju → `Room.id` (dopasowanie po `Room.name`, bez rozróżniania wielkości liter) → `sender_id` (dopasowanie po `SenderProfile.room_id`), **z pominięciem kandydatów bez `ClientCapability.SPEAKER`** — mowa przekierowana na klienta czysto tekstowego nie miałaby jak się odtworzyć. Błąd (bez przekierowania) przy braku dopasowania nazwy, braku odbiornika z głośnikiem lub niejednoznaczności (wielu odbiorników w tym samym pokoju). Treść udanego wyniku niesie **nowe ramowanie dostawy** — prompt systemowy powstał przed turą i nie wie o przekierowaniu, a wyniki narzędzi i tak wracają do modelu w pętli ReAct. Zwraca `ToolResult.redirect_sender_id` — patrz sekcja 3.5 dla mechanizmu w kernelu.

### 3.5 `server/voice` — pipeline głosowy satelit

Peer `WorldEngine`, nie jego część ani konsument — oba znają wyłącznie opaque
`sender_id` przepływający przez kernel, nigdy się nawzajem nie importują
(weryfikacja: `docs/onboarding.md`, sekcja 3). Jedyny punkt styku z kernelem to
publiczny kontrakt `AgentEngine` — dokładnie ten sam, z którego korzysta
`network/routes/chat.py`.

- **Model doręczenia — jednokierunkowy, "wyślij i zapomnij"**: `AgentEngine.start_interaction()`
  (`agent/engine.py`) tylko odpala turę w tle i od razu wraca — **nie**
  subskrybuje `EventBus`, nie czeka na wynik (w przeciwieństwie do
  `interact()`/`interact_stream()`, używanych przez HTTP). Doręczenie idzie
  wyłącznie przez `EventBus`: `VoiceConnection` (`voice/gateway.py`)
  subskrybuje `CHAT_CHUNK`/`CHAT_DONE`/`CHAT_ERROR`/`CHAT_CANCELLED` **przez
  cały czas życia połączenia WS**, niezależnie od tego, czy to połączenie
  zainicjowało bieżącą turę — to właśnie ta ciągłość pozwala na przekierowanie
  odpowiedzi do innego `sender_id` (patrz `speak_in_room` wyżej i akapit
  o `ToolResult.redirect_sender_id` niżej).
- **`ToolResult.redirect_sender_id`** (`agent/llm.py`): mechaniczne pole — kernel nie interpretuje jego znaczenia, tylko zmienia **`target_client_id`** (adres dostawy) na resztę tury (`agent/engine.py`, `_generate_in_background`). Każde zdarzenie `CHAT_*`/`TOOL_CALL_*` niesie **dwa niezależne identyfikatory**: `session_id` (tożsamość rozmowy/pamięci — **nigdy się nie zmienia**, filtrują po nim `watch_session`/`interact_stream`/Web UI) oraz `target_client_id` (adres dostawy — filtrują po nim odbiorcy fizyczni, `voice/gateway.py`). Historia (`MemoryManager`) zawsze pod oryginalnym `session_id` — przekierowanie zmienia wyłącznie dostawę, nigdy właściciela konwersacji.

  **Rewizja (2026-08-22)**: wcześniej obie role pełniło jedno pole `session_id` (`effective_session_id`), co działało wyłącznie dzięki temu, że dla satelit `session_id == sender_id`. Dla klienta, u którego te wartości się różnią (przeglądarka: sesja czatu vs `sender_id` z localStorage), przekierowanie publikowało zdarzenia pod tagiem, którego nikt nie słuchał — **odpowiedź znikała bez błędu**. Rozdzielenie usunęło też potrzebę dawnego dual-castu zdarzeń terminalnych (istniał tylko po to, by `interact_stream()` nie zawisł, gdy tag dostawy uciekł). `voice/gateway.py::_on_done` obsługuje dziś jawnie obie role: adresat mówi zgromadzony tekst, a inicjator, któremu turę dostarczono gdzie indziej, wraca do nasłuchu zamiast zostać w `PROCESSING`.
- **`VoiceSession`** (`voice/session.py`): czysty automat stanu treści (`LISTENING_WAKEWORD` → `RECORDING_UTTERANCE` → `PROCESSING` → `SPEAKING` → z powrotem), zero wiedzy o WebSocket/EventBus — testowalny w izolacji (`tests/test_voice_pipeline.py`). `reset_to_listening()` to awaryjny powrót do nasłuchu wołany przez gateway po `CHAT_ERROR`/`CHAT_CANCELLED`, żeby sesja nigdy nie utknęła w `PROCESSING`/`SPEAKING` na zawsze.
- **Protokół WS** (`shared/voice_protocol.py` — **od tej sesji w `packages/shared`, nie w `server/voice/`**: kontrakt ramek, współdzielony przez dwie niezależne usługi, `server` i `desktop_satellite`, patrz sekcja 3.6): ramki binarne = surowe PCM16 mono (bez kodeka) w obie strony; ramki tekstowe JSON = control-plane (`hello`/`utterance_end`/`playback_done` od satelity, `wake_detected`/`play_stop_tone`/`tts_start`/`tts_end`/`error` od serwera). Dźwięki wake/stop-tone są lokalne (wypalone w firmware satelity/generowane przez klienta desktopowego), nigdy strumieniowane z serwera.
- **VAD po stronie satelity**: to satelita (nie serwer) decyduje o końcu wypowiedzi (min. 1.5s ciszy) i wysyła `utterance_end` — świadoma decyzja architektoniczna (satelita i tak musi wiedzieć, kiedy przestać nagrywać/streamować, żeby nie wysyłać ciszy w nieskończoność).
- **STT/TTS** — protokół (`voice/stt.py`::`BaseSTTProvider`, `voice/tts.py`::`BaseTTSProvider`) to mirror `BaseLLMProvider` (`agent/llm.py`), zostaje w `voice/`. Od 2026-08-21 (sesja: parytet CRUD z LLM) `server/ai/stt`/`server/ai/tts` mają **pełny rejestr wielu nazwanych instancji**, mirror `ai/llm/registry.py`::`BackendRegistry` — `STTRegistry`/`TTSRegistry` (pliki `data/stt_backends/*.json`+`data/active_stt_backend.json`, `data/tts_backends/*.json`+`data/active_tts_backend.json`), `STTFactory`/`TTSFactory` (`create_provider`+`get_all_schemas()`, Single Source of Truth schematów, mirror `LLMFactory`). Konkrety: `GroqSTTProvider` (`ai/stt/providers.py`, `AsyncGroq.audio.transcriptions.create()`, modele `whisper-large-v3-turbo`/`whisper-large-v3`, `language="pl"` — surowe PCM16 owijane w minimalny nagłówek WAV, `_pcm_to_wav()`, bo Groq przyjmuje pliki audio, nie goły strumień) i `ElevenLabsTTSProvider` (`ai/tts/providers.py`, `AsyncElevenLabs.text_to_speech.convert()`, `output_format="pcm_16000"` — **dokładnie** nasz format przewodowy, zero resamplingu; `model_id="eleven_multilingual_v2"`, jedyny model jawnie potwierdzony jako wspierający polski). Puste `api_key` w opcjach instancji TTS = łagodna degradacja do `MockTTSProvider` (cisza proporcjonalna do długości tekstu — nieszkodliwy fallback). **STT jest asymetryczne** (rewizja z 2026-08-21, po sesji testowej end-to-end): pusty `api_key` w `STTFactory.create_provider` rzuca `STTNotConfiguredError` zamiast po cichu zwracać `MockSTTProvider` — satelita nagrywa realną mowę, więc podstawienie sfabrykowanego tekstu ("Testowa wiadomość głosowa.") wygenerowałoby prawdziwą turę agenta na podstawie czegoś, czego użytkownik nigdy nie powiedział (mylące w przeciwieństwie do jawnie fałszywej odpowiedzi Mock LLM/ciszy Mock TTS). `VoiceSession.handle_utterance_end()` łapie ten wyjątek, wysyła `error` do satelity (`SatelliteLink.send_error()`, nowa metoda protokołu, reużyta też przez `gateway.py::_on_error_or_cancelled`) i wraca do nasłuchu — **bez** wywołania `on_transcript`/`AgentEngine.start_interaction()`. `MockSTTProvider` zostaje w kodzie wyłącznie jako jawny wybór w testach jednostkowych, bez osobnego przełącznika `enabled`.

  REST: `voice/provider_routes.py`::`create_voice_providers_router` — pełny CRUD mirror `network/routes/providers.py` (LLM): `GET .../stt/providers/schemas`, `GET/POST/PUT .../stt/providers[/active]`, `DELETE .../stt/providers/{id}` i analogicznie `.../tts/providers*`. Powód: użytkownik planuje lokalne rozwiązania STT/TTS obok Groq/ElevenLabs — konkretny drugi kandydat w ręku, warunek YAGNI-out spełniony (w odróżnieniu od wcześniejszej sesji, gdzie jeden realny dostawca każdego typu uzasadniał tylko płaski, jednosslotowy config). Ten sam plik trzyma **shim kompatybilności** `GET/PUT /api/v1/voice/providers/config` — dzisiejszy, płaski kontrakt `voice_config.js` (bez zmian we froncie w tej sesji — UI świadomie odłożone), zbudowany nad *aktywną* instancją STT + *aktywną* instancją TTS (`STTRegistry.update_instance`/`TTSRegistry.update_instance`, nadpisuje `options` w miejscu, bez zmiany ID). Pierwsze uruchomienie po tej zmianie: best-effort migracja z legacy `data/voice/config.json` (`VoiceProvidersConfig`) do jednej domyślnej instancji per typ (`stt_groq_default`/`tts_elevenlabs_default`) — istniejące klucze API użytkownika nie giną.

  `voice/` trzyma nie te konkrety wprost, tylko `STTRouter`/`TTSRouter` (`ai/stt/router.py`/`ai/tts/router.py`, patrz wyżej "Singleton-router per moduł") — cache klucz to `(active_id, options)`, **nie sam `active_id`**: w odróżnieniu od LLM (gdzie REST nigdy nie edytuje pól istniejącej instancji, tylko create/switch/delete), shim kompatybilności edytuje `options` aktywnej instancji w miejscu, więc sam niezmieniony `active_id` nie gwarantuje niezmienionej konfiguracji (błąd znaleziony i naprawiony w tej samej sesji testem regresyjnym, `tests/test_ai_routers.py`). Efekt: zmiana aktywnego dostawcy/klucza/modelu STT/TTS (przez shim albo nowy CRUD) działa **od razu, bez restartu serwera**.

  **Świadomie NIE zbudowano** wspólnej, generycznej klasy rejestru w `packages/shared` współdzielonej przez LLM/STT/TTS — mimo że to już trzecie niemal identyczne miejsce (`BackendRegistry`/`STTRegistry`/`TTSRegistry`). Prawdziwa konsolidacja DRY ma sens dopiero gdy wzorzec się ustabilizuje po dodaniu realnego drugiego typu STT/TTS (Boy Scout Rule przy kolejnej zmianie, nie spekulacyjnie z góry).
- **`wakeword.py`**: `OnnxWakeWordDetector` — realny detektor oparty o wytrenowany model `.onnx` (biblioteka `livekit-wakeword`, ekstrakcja cech mel-spektrogram+embedding wbudowana w pakiet — tylko `numpy`+`onnxruntime` jako zależności runtime, bez `torch`). Kroczący bufor ~2s audio, inference co ~320ms (stride), próg pewności z `Settings.wakeword_threshold`. Koszt inference zmierzony empirycznie: ~20ms/wywołanie na CPU — przy tej skali projektu (jednoosobowy, kilka satelit) zostawione jako wywołanie synchroniczne w `WakeWordDetector.process()` (bez `run_in_executor`); do rewizji, gdyby liczba jednoczesnych satelit realnie wzrosła. `ThresholdEnergyWakeWordDetector` (sekwencja głośnych ramek, nie prawdziwe rozpoznawanie słowa) to dziś **fallback** — używany, gdy `Settings.wakeword_model_path` puste albo plik nie istnieje (`main.py`, `_build_wakeword_detector_factory`, łagodna degradacja jak przy braku configu Home Assistant), oraz w testach automatu stanu (`test_voice_pipeline.py`). Detekcja odbywa się **wyłącznie po stronie serwera** (`VoiceSession.handle_audio_frame()`, stan `LISTENING_WAKEWORD`) na surowym PCM streamowanym przez satelitę — VAD po stronie satelity (`SilenceVadDetector`, sekcja 3.7) to zupełnie inny, niezależny mechanizm (koniec wypowiedzi, stan `RECORDING_UTTERANCE`), nieuczestniczący w ogóle w detekcji wake-worda. **Score z każdego inference** (dotąd liczony i odrzucany bez śladu) loguje się teraz na poziomie DEBUG (`"Wake-word score: {score:.3f} [próg: ...]"`) — INFO zalałoby konsolę przy inference co ~320ms. Poziom logowania steruje `Settings.debug` (dotąd martwe pole, podpięte w `main.py` PRZED `setup_logging()` — wymaga wczytania configu wcześniej niż dotąd, stąd `load_settings()` przeniesione z `main()` na poziom modułu).
- **Rewizja (2026-08-21) — centralna konfiguracja wake-word/VAD + rename zakładki na "Klienci"**: decyzja architektoniczna tej sesji — satelita zostaje maksymalnie cienki. Wake-word detection zostaje w 100% po stronie serwera (już było — patrz wyżej). VAD **algorytm** zostaje lokalnie na satelicie (celowo — centralizacja decyzji dodałaby rundtrip bez korzyści, satelita i tak musi wiedzieć lokalnie, kiedy przestać streamować), ale jego **parametry** (`silence_duration_ms`/`amplitude_threshold`, dotąd hardcoded defaulty konstruktora `SilenceVadDetector`, nigdy nawet nie w pliku configu satelity) są odtąd centralnie skonfigurowane na serwerze (`Settings.vad_silence_duration_ms`/`vad_amplitude_threshold`) i wysyłane satelicie **raz, zaraz po handshake** — nowa wiadomość protokołu `ServerMessageType.CLIENT_CONFIG` (`shared/voice_protocol.py`), obsłużona w `VoiceConnection._handshake()` (serwer) i `SatelliteSession._await_client_config()` (satelita, `services/desktop_satellite/session.py` — timeout 3s + fallback do lokalnych defaultów 1500ms/500 dla starszego serwera bez tej wiadomości, łagodna degradacja jak wszędzie indziej w projekcie). `SatelliteSession` przyjmuje teraz `vad_factory: Callable[[float, int], SilenceVadDetector]` zamiast gotowej instancji — konstrukcja VAD-u przesunięta z `main.py::run_forever()` do momentu otrzymania configu.

  **Przy okazji naprawiony bug**: `_build_wakeword_detector_factory()` zamykał `threshold` w closure przy starcie procesu — zmiana przez UI nie działałaby bez restartu, niespójnie z resztą projektu (LLM/STT/TTS routery: "instant effect"). Teraz `factory()` woła `load_settings()` na świeżo przy każdym połączeniu.

  **REST**: `GET/PUT /api/v1/voice/client-config` (`voice/routes.py`, `create_voice_status_router`) — jeden endpoint na wszystkie trzy pola (próg wake-worda + oba parametry VAD), `PUT` robi `model_copy(update={...})` tylko tych pól na pełnym `Settings` (mirror wzorca `network/routes/prompts.py`), zero ryzyka nadpisania niepowiązanych pól (port, host, itd.).

  **Web UI**: zakładka dawniej "Głos" przemianowana na **"Klienci"** (`settings.js`/`dashboard.js` — `data-section="voice"` zostaje bez zmian, tylko widoczny label) — dostała nową sekcję "Konfiguracja klienta" (`voice_config.js`, nad istniejącą listą): próg wake-worda jako % (konwersja ↔ float 0-1 tylko w JS), oba pola VAD w ms/amplitudzie, jeden "Zapisz". Domyślna wartość pola `wakeword_threshold` w kodzie podniesiona z `0.5` na `0.65` — **nie dotyka** istniejących, już wytuningowanych plików `settings.json` (np. `0.39` z sesji treningowej modelu `regis.onnx`), wpływa tylko na świeże instalacje bez configu.

- **Rewizja (2026-08-22) — "Klienci" jako dashboard na żywo (nie tylko config)**: druga iteracja tej samej sesji — użytkownik chciał, żeby zakładka pokazywała też **listę wszystkich klientów** z ich statusem w czasie rzeczywistym (online/offline, stan sesji, wake-word wykryty + pewność), nie tylko formularz. Zastosowany **dokładnie ten sam wzorzec push-live**, co przy rewizji Web UI dla czatu (sekcja 4.1, `AgentEngine.watch_session()`), tylko dla zdarzeń satelitów zamiast tur czatu:
  - **`server/voice/events.py`** (nowy plik) — `VoiceEventType`: `SATELLITE_CONNECTED`/`SATELLITE_DISCONNECTED`/`SATELLITE_STATE_CHANGED`/`SATELLITE_WAKE_WORD_DETECTED`. Publikowane przez **ten sam, współdzielony** `agent_engine.event_bus` co `ServerEventType.CHAT_*` — osobna przestrzeń nazw, zero kolizji, zero nowego obiektu magistrali.
  - **`VoiceSession`** (`voice/session.py`) dostaje wstrzyknięty `publish_event` (jedyne miejsce zmiany stanu to teraz prywatna `_set_state()`, która zawsze publikuje `SATELLITE_STATE_CHANGED`) — `reset_to_listening()` stało się `async` (musiało, żeby publikować). Wake-word detected publikuje też `score` — stąd `WakeWordDetector.last_score` (nowa właściwość Protocol, `None` dla `ThresholdEnergyWakeWordDetector`, realna wartość z ostatniego inference dla `OnnxWakeWordDetector` — score był już liczony i logowany DEBUG, teraz dodatkowo eksponowany).
  - **`sender_states: dict[str, str]`** (`main.py`, mirror `connected_sender_ids`) — snapshot `SessionState.name` per `sender_id`, mutowany w `VoiceConnection._publish_voice_event()` przy okazji publikacji, czytany przez `GET /api/v1/voice/clients/status` (hydratacja przy pierwszym załadowaniu strony). `SATELLITE_CONNECTED`/`DISCONNECTED` publikowane wprost z `voice_endpoint()` (`gateway.py`), obok istniejącej mutacji `connected_sender_ids`.
  - **`GET /api/v1/voice/clients/watch`** (`voice/routes.py`) — SSE, ale **globalny** (jeden strumień dla wszystkich `sender_id` naraz, w odróżnieniu od per-sesyjnego `.../chat/sessions/{id}/watch`), bo dashboard pokazuje wszystkich klientów jednocześnie. Logika subskrypcji wydzielona do osobnej funkcji `watch_voice_events()` specjalnie po to, żeby była testowalna bezpośrednio (mirror `AgentEngine.watch_session()`), bez owijania w `StreamingResponse`.
  - **Web UI** (`voice_config.js`): lista podzielona na "Oczekujący" (jak dawniej) i **nowe** "Zarejestrowani" (dotąd w ogóle niepokazywani w tej zakładce) — karty mirror `.agent-provider-card`/`.agent-provider-card-check` (`providers.css`). **Zasada layoutu** (utrwalona jako pamięć projektu po jawnej prośbie użytkownika, patrz `feedback_layout_stability_ui`): stały 32×32 kwadrat na ikonę mikrofonu (tylko `background-color`/`color` się przełącza), stały `min-width` na tekst pewności/stanu — dynamiczna treść (wake-word na ~1.5s, `setTimeout` w `_onClientWakeWordDetected`) nigdy nie zmienia wymiarów karty. Pola configu (próg/VAD) zmienione z `type="number"` na `type="text"` — usuwa strzałki góra/dół bez dodatkowego CSS.
  - Zweryfikowane na żywo (Browser pane + realne połączenie WS przez `websockets`): badge online/offline zmienia się w przeglądarce bez odświeżenia przy connect/disconnect; CSS `.is-detected`/`.is-visible` potwierdzone jako poprawnie stylowane (`getComputedStyle`). `services/server/scripts/voice_satellite_sim.py` zaktualizowany o odbiór `client_config` zaraz po handshake (inaczej desynchronizacja z resztą protokołu testowego).
- **Brak uwierzytelniania WS**: `WS /ws/voice/{sender_id}` nie weryfikuje w żaden sposób tożsamości łączącego się klienta — spójne z resztą systemu (opaque `sender_id` bez auth), świadome założenie modelu zaufanej sieci lokalnej, do rewizji dopiero przy realnej potrzebie (np. wystawienie serwera poza LAN).
- **`connected_sender_ids`** (od tej sesji, `main.py`+`gateway.py`+`routes.py`): zwykły, współdzielony `set[str]` (bez locka — jeden wątek asyncio) wypełniany przez `voice_endpoint()` (`add` po `websocket.accept()`, `discard` w `finally`), czytany przez `GET /api/v1/voice/connected` (`routes.py`). Mechaniczny fakt "kto ma żywe połączenie WS teraz" — zero wiedzy o rejestracji/pokoju (to należy do `World`). **Monitorowanie tego stanu w Web UI żyje w zakładce Głos** (`voice_config.js`, sekcja "Satelity"), **nie Świat** — pierwsza wersja umieściła listę oczekujących w panelu Nadawcy (`extensions/ha/satellites_panel.js`), co dawało zakładce Świat drugą odpowiedzialność nienależącą do niej ani koncepcyjnie, ani pod maską (poprawione tego samego dnia po informacji zwrotnej).

  **Rejestracja nadawców, ostateczny podział (ta sama sesja, druga iteracja po feedbacku)**: pierwszy kontakt z nieznanym nadawcą (satelita podłączona przez WS, albo ID tej przeglądarki) dzieje się **wyłącznie w zakładce Głos** — przycisk "Zarejestruj" woła `POST /api/v1/world/senders` od razu, z `room_id: null` (World i tak przyjmuje pusty pokój). Zakładka **Świat** (panel Nadawcy, `satellites_panel.js`) stała się czystą listą już zarejestrowanych — zero tworzenia nowych wpisów (usunięty formularz "+ Nowa rejestracja" i skrót "Zarejestruj tę przeglądarkę", oba przeniesione do Głosu), tylko picker pokoju per wiersz (`renderSelectMarkup`/`initSelect`, mirror `devices_panel.js`) wołający ten sam `POST /api/v1/world/senders` jako upsert (`WorldEngine.register_sender`: "rejestruje lub nadpisuje") do zmiany przypisania pokoju, plus usuwanie. Cross-domenowe wywołanie zapisu (Głos woła World-owy endpoint) jest świadomie dopuszczone — granicę narusza dopiero *renderowanie* cudzej domeny w niewłaściwym pliku/zakładce, nie samo wywołanie REST innej domeny z UI.
- **`services/server/scripts/voice_satellite_sim.py`**: symulator satelity (Python + `websockets`) przechodzący cały cykl protokołu bez żadnego sprzętu — dziś głównie do testów regresyjnych; realny klient istnieje w `services/desktop_satellite/` (sekcja 3.7).

### 3.6 Warstwa Wspólna (`packages/shared/src/shared`)
- **`ConfigStore` (`config.py`)**: Centralny zarządca persystentnej konfiguracji w formacie JSON z automatyczną walidacją i domyślnymi wartościami.
- **`EventBus` (`event_bus.py`)**: Asynchroniczna magistrala zdarzeń pub/sub (`subscribe`/`publish`). **W pełni wpięta w przepływ strumieniowania** — `AgentEngine` publikuje zdarzenia `ServerEventType.CHAT_CHUNK/DONE/ERROR/CANCELLED` oraz `TOOL_CALL_START/TOOL_CALL_RESULT` (kroki pętli ReAct), otagowane `session_id` **i** `target_client_id` (patrz sekcja 3.5, `ToolResult.redirect_sender_id`), a `interact_stream` subskrybuje je i tłumaczy z powrotem na strumień ustrukturyzowanych `StreamEvent` (`agent/engine.py`) dla wywołującego. **Treść `CHAT_ERROR` jest zawsze ogólna** (`AgentEngine._generate_in_background`, `except Exception`) — pełny techniczny szczegół wyjątku trafia wyłącznie do `logger.error` (konsola + `data/logs/regis.log`), nigdy do `EventBus`/pamięci sesji/UI. Powód: surowe błędy API dostawców LLM potrafią nieść wewnętrzne dane konta (zaobserwowane na żywo: ID organizacji Groq w treści błędu 429) — nie powinny wyciekać do żadnego z trzech odbiorców zdarzenia (SSE Chat UI, `interact()`, `voice/gateway.py`::`_on_error_or_cancelled` wysyłający `detail` do satelity), które wszystkie czerpią z tego samego payloadu, więc jedna sanityzacja u źródła zabezpiecza wszystkie na raz. Dzięki temu rdzeń nie zna bezpośrednio odbiorców — dziś dwóch: SSE (HTTP, `routes/chat.py`, subskrypcja per-request) i WS satelit głosowych (`server/voice/gateway.py`, subskrypcja ciągła per-połączenie, patrz sekcja 3.5). `routes/chat.py` serializuje `StreamEvent` na ramki SSE z polem `type` (`chunk`/`tool_start`/`tool_result`). Ustrukturyzowany ślad kroków (`ToolStepPayload`: `call_id`/`name`/`text_offset`/`arguments`/`content`/`is_error`) trafia też — gdy tura użyła narzędzi — do `metadata.steps` finalnej wiadomości `assistant` w `MemoryManager`, więc Web UI potrafi odtworzyć całe drzewko ReAct (tekst/COT przeplecione z wywołaniami narzędzi) zarówno na żywo, jak i po powrocie do historii sesji.
- **`contracts.py`**: Definicje obiektów transferu danych (DTO) współdzielonych przez serwer i konsolę WWW:
  - **System**: `HealthResponse`.
  - **Dostawcy LLM**: `LLMProviderDTO`, `LLMProviderListResponse`, `SelectLLMProviderRequest`, `CreateLLMProviderRequest` oraz generyczna specyfikacja opcji (`ProviderOptionSpec`, `ProviderTypeSpecDTO`, `ProviderMetadataResponse`) — schema-driven forma uzasadniona realną wymiennością backendu LLM (Ollama/OpenRouter).
  - **Czat i sesje**: `ChatMessageDTO`, `SendChatMessageRequest` (w tym opaque `sender_id`), `ChatResponseDTO`, `ChatSessionSummaryDTO`, `ChatSessionHistoryResponse`, `ChatSessionListResponse`, `CancelChatApiRequest`.
  - **Profile promptu Świata** (CRUD, do 3, `world/routes.py`): `PromptDTO`, `PromptListResponse`, `CreatePromptRequest`, `UpdatePromptRequest`. **Fallback promptu kernela** (jedna wartość, `network/routes/prompts.py`): `AgentDefaultPromptDTO`.
  - Prywatne słownictwo Home Assistant/satelit (config, katalog, grupy, rejestracje) żyje lokalnie w `world/dto.py`, nie tutaj — nie ma potrzeby generycznego kształtu skoro istnieje dokładnie jeden silnik.
- **`logging.py`**: Jednolita konfiguracja logów dla całego monorepo z ustandaryzowanymi nazwami kategorii (`regis.main`, `regis.agent`, `regis.world`, itp.). `setup_logging(level, log_file=None)` — konsola zawsze (kolorowany `MinimalColorFormatter`), opcjonalnie też plik z rotacją (`RotatingFileHandler`, 5 MB × 3 kopie, `PlainFileFormatter` bez kodów ANSI, pełna data). `main.py` przekazuje `data/logs/regis.log` (gitignorowane jak reszta `data/`) — dodane 2026-08-21, bo błędy tury (np. surowa treść odpowiedzi błędu API dostawcy LLM, potencjalnie z wewnętrznym ID organizacji) świadomie **nie** trafiają wprost do użytkownika (patrz niżej, `AgentEngine._generate_in_background`) i bez pliku ginęłyby bezpowrotnie po przewinięciu terminala.
- **`voice_protocol.py`**: Kontrakt ramek WS satelity (`SatelliteMessageType`/`ServerMessageType`/`SAMPLE_RATE_HZ`/`SAMPLE_WIDTH_BYTES`/`CHANNELS`) — przeniesiony tu z `server/voice/protocol.py`, bo od `desktop_satellite` (sekcja 3.7) jest to kontrakt między dwiema niezależnymi usługami, nie szczegół jednej z nich (ten sam powód, dla którego DTO REST żyją w `contracts.py`, nie w `server/network/`).
- **`discovery.py`**: Kontrakt UDP auto-discovery — `DISCOVERY_UDP_PORT`, `DISCOVERY_MAGIC` (odsiewa obcy ruch UDP na tym porcie) i czyste funkcje `encode_beacon`/`decode_beacon` (JSON `{"service", "port"}`). Współdzielony przez `server/discovery.py` (nadawca) i `desktop_satellite/discovery.py` (odbiorca) — bez uwierzytelniania, spójnie z modelem zaufanej sieci lokalnej przyjętym dla `WS /ws/voice/{sender_id}` (sekcja 5).

### 3.7 `desktop_satellite` — realny klient satelity desktopowej (`services/desktop_satellite/src/desktop_satellite`)

Pierwsza realna (nie-symulowana) implementacja satelity — długo działający proces
konsolowy na Windows/Linux, niezależna usługa `services/*` (nie importuje
niczego z `services/server`, łączy je wyłącznie `packages/shared` i protokół WS).

- **`protocol_client.py`**: `ProtocolClient` — cienki klient `websockets` kodujący/dekodujący ramki zgodnie z `shared/voice_protocol.py`, symetryczny do `VoiceConnection` (`server/voice/gateway.py`) z odwróconą rolą klient/serwer.
- **`session.py`**: `SatelliteSession` — klienckie odbicie automatu `VoiceSession`: `LISTENING_WAKEWORD` → (odbiór `wake_detected` od serwera — wake-word nadal wykrywa **serwer**, dziś placeholder `ThresholdEnergyWakeWordDetector`, satelita tylko ciągle strumieniuje mikrofon) → `RECORDING_UTTERANCE` (lokalny `vad.SilenceVadDetector` decyduje, kiedy wysłać `utterance_end` — zgodnie z decyzją "VAD po stronie satelity" niżej) → `PROCESSING` (mikrofon wstrzymany, ten sam powód co po stronie serwera: uniknięcie nagrywania własnego odtwarzania) → `SPEAKING` (odbiór `tts_start..tts_end`, odtworzenie, `playback_done`) → powrót do nasłuchu. Czysty automat + wstrzyknięte zależności (`link`/`speaker`/`vad`), testowalny bez gniazda/sprzętu (`tests/test_session.py`), tym samym wzorcem co serwerowy `VoiceSession`.
- **`vad.py`**: `SilenceVadDetector` — czysta klasa (mirror stylu `ThresholdEnergyWakeWordDetector`), wyzwala się po skonfigurowanym czasie ciągłej ciszy licząc od startu nagrywania (nie tylko po realnej mowie — **poprawione 2026-08-20**: wcześniejsza wersja czekała na choć jedną głośną ramkę, więc satelita wisiała bez końca w `RECORDING_UTTERANCE`, jeśli użytkownik nic nie powiedział po wake-wordzie; sam wymóg pełnego progu ciszy już chroni przed przedwczesnym wyzwoleniem). Testowalna w izolacji (`tests/test_vad.py`).
- **`audio.py`**: `MicCapture`/`SpeakerPlayback` przez `sounddevice`+`numpy` (PortAudio, Windows/Linux) — PCM16 mono 16 kHz, ramki 20 ms. `SpeakerPlayback.play_cue()` **(2026-08-20)** odtwarza wake/stop-tone preferencyjnie jako wbudowany dźwięk systemowy Windows Speech Recognition (`C:\Windows\Media\Speech On.wav`/`Speech Sleep.wav` — te same dźwięki, które kiedyś towarzyszyły Cortanie; własność użytkownika/Windows, nigdy nie kopiowane do repo, odtwarzane przez `winsound.PlaySound`), z fallbackiem do `synth_tone()` (lokalnie syntezowany sinusoidalny beep) na Linux albo gdy plik nie istnieje. Zero strumieniowania dźwięku z serwera w obu wariantach.
- **`main.py`**: CLI (`--server-url`/`--sender-id`/`--log-level`, wszystkie opcjonalne), pętla reconnect z backoffem (log + `asyncio.sleep`), czyste zamknięcie mikrofonu na `KeyboardInterrupt`.
- **`config.py`**: `SatelliteSettings` (`ConfigStore`+`get_service_root`, mirror `server/config.py`) — `sender_id: str` z `default_factory=uuid.uuid4`, trwale zapisywany w `services/desktop_satellite/config/settings.json` przy pierwszym uruchomieniu (brak pliku). Bez flagi `--sender-id` `main.py` używa `load_or_create_sender_id()` — ten sam UUID przy każdym kolejnym starcie, bez ręcznego wpisywania.
- **`discovery.py`**: `discover_server()` — nasłuchuje UDP broadcast serwera (`shared/discovery.py`), buduje `ws://{ip nadawcy}:{port z beaconu}/ws/voice`. Bez flagi `--server-url` `main.py` wywołuje to przed każdą próbą połączenia (bez cachowania ostatniego znanego adresu — KISS, broadcaster serwera działa non-stop, ponowne odkrycie kosztuje najwyżej jeden interwał rozgłoszenia).
- **Wake-word i STT/TTS: realne od tej sesji** (serwerowy `OnnxWakeWordDetector`, `GroqSTTProvider`/`ElevenLabsTTSProvider`, sekcja 3.5) — klient desktopowy dowodzi poprawności całego protokołu, lokalnego VAD i realnego pipeline'u głosowego (transkrypcja/synteza wymagają wklejenia własnych kluczy API w Web UI, zakładka Głos — bez kluczy łagodna degradacja do Mock*).

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
       |                       |                     |--- build_messages (system_prompt = World lub fallback) ->|
       |                       |                     |--- generate_stream(tools) ----------->|                 |
       |                       |                     |--- publish CHAT_CHUNK ---------------------------------->|
       |<-- sse data chunk ----|<-- yield chunk -----|<-- (subskrypcja EventBus) ------------------------------|
       |                       |                     |--- add_assistant_msg -->|             |                 |
       |                       |                     |--- publish CHAT_DONE ----------------------------------->|
       |<-- sse data [DONE] ---|<--------------------|                   |                   |                 |
```

**Rewizja (2026-08-21) — Web UI przeszło na "wyślij i zapomnij" + stały kanał obserwujący, symetrycznie z satelitą głosową**: Powyższy diagram (`POST /chat/stream`, subskrypcja `EventBus` żyjąca tylko na czas jednej tury, kończąca się na `CHAT_DONE`) opisuje wciąż istniejący, ale **już nieużywany przez Web UI** kontrakt — zostaje dla ewentualnych innych konsumentów REST. Powód rewizji: karta przeglądarki widziała tokeny na żywo wyłącznie dla tury, którą **sama** zainicjowała tym samym żądaniem SSE — turę odpaloną gdzie indziej (satelita, cron, inna karta, ten sam `session_id`) widziała dopiero po ręcznym odświeżeniu strony, bo nic nie łączyło jej z `EventBus` poza czasem trwania własnego żądania.

Naprawione przez pełne zrównanie architektury Web UI z satelitą (`voice/gateway.py`, `VoiceConnection`):
- **`AgentEngine.watch_session(session_id)`** (`agent/engine.py`) — pasywna, długożyjąca subskrypcja `EventBus` po `session_id`, współdzieląca z `interact_stream()` jeden helper (`_subscribe_session_events`). W odróżnieniu od `interact_stream()` nie odpala żadnej tury i nie kończy się na `done`/`error`/`cancelled` — przekazuje każde zdarzenie dalej i czeka na kolejne, aż wywołujący przerwie iterację (rozłączenie SSE). Wystawiona przez `GET /api/v1/chat/sessions/{id}/watch` (`routes/sessions.py`).
- **`ServerEventType.CHAT_USER_MESSAGE`** (`events.py`) — nowe zdarzenie, publikowane w `_generate_in_background()` zaraz po zapisaniu pytania użytkownika w pamięci. Dotąd treść promptu nigdy nie trafiała na `EventBus` (tylko do `MemoryManager`) — obserwator sesji zainicjowanej gdzie indziej nie miał jak dowiedzieć się, o co spytano, bez przeładowania historii.
- **`POST /api/v1/chat/send`** (`routes/chat.py`) — REST-owy wrapper na `AgentEngine.start_interaction()` (dotąd używane wyłącznie przez `voice/gateway.py`), zwraca 202 natychmiast. `chat.js::handleSendMessage()` woła wyłącznie to — Web UI nie ma już żadnej "własnej", uprzywilejowanej ścieżki renderowania: własna wysłana wiadomość i wiadomość satelity wyglądają dla klienta identycznie, obie przychodzą przez ten sam, zawsze otwarty `watchSession()`.
- **`ChatView`** (`chat.js`) otwiera jeden kanał `watchSession()` per aktywna sesja (przy wejściu w Chat i przy każdej zmianie sesji, z automatycznym reconnectem) — to jedyne źródło renderowania wiadomości/streamingu/kroków ReAct. Osobny, dużo rzadszy poll (`checkForNewSessions`, ~4s) zostaje wyłącznie do wykrywania **nowych** sesji (kanał jest per-sesja, nie widzi tego, co jeszcze nie istnieje w popoverze) — treść już nie idzie tą ścieżką. Dawny fallback-polling historii (`startPolling`, nadpisujący cały tekst co 1.5s) został usunięty — "dołączenie" do sesji już generującej (np. po przeładowaniu strony) korzysta z partial-buffera z `GET .../history` jako startowego snapshotu, a dalsze tokeny/kroki dokłada już `watchSession()` na żywo (częściowo domyka gap z punktu "Zaplanowane" niżej — kroki SPRZED dołączenia nadal niewidoczne, te PO już tak).
- Zweryfikowane na żywo (Browser pane + `curl` symulujący satelitę wołający `POST /api/v1/chat/send` bezpośrednio): wiadomość i pełna odpowiedź (włącznie z błędem rate-limitu Groq, poprawnie sanitizowanym) pojawiły się w already-otwartej karcie bez żadnego odświeżenia.

### 4.2 Pętla Agentyczna (ReAct — Tool Calling)
```text
AgentEngine       WorldEngine (build)              HomeAssistantClient (invoke)
     |                    |                                |
     |--- build(sender_id) -->|                             |
     |                    |--- list_devices() ------------>|
     |                    |<-- [Device] --------------------|
     |<-- tool_definitions, system_prompt, dispatch --------|
     |                       |                        |
     |--- generate_stream(messages+system_prompt, tools) ---------------------->|
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
- **Modalność to capability klienta, nie parametr wywołania (rewizja 2026-08-22)**: Historia tej decyzji ma trzy etapy. (1) Pierwsza wersja trzymała kanał w `SatelliteRegistration.channel` — trwały config administrowany ręcznie, mogący rozjechać się z rzeczywistością. (2) Zrewidowane na `voice_mode: bool` — efemeryczny parametr wywołania dostarczany przez `server/voice` przez kernel do `WorldEngine.build()`, bo to gateway strukturalnie wie, czy interakcja jest głosowa. (3) **Zrewidowane ponownie**: `voice_mode` opisywał **wejście** ("przyszło głosem"), a sterował framingiem **wyjścia** ("odpowiadaj krótko, bo to będzie czytane"). To nie jest to samo pytanie — cel dostawy potrafi się zmienić w połowie tury (`speak_in_room`), a `system_prompt` powstaje raz, przed jej startem, i już tego nie nadgoni. Dodatkowo flaga zmuszała kernel do *przenoszenia* przez siebie wiedzy o kanale, choć nic z nią nie robił.

  Dziś `SenderProfile.capabilities: frozenset[ClientCapability]` (`mic`/`speaker`/`text`) jest **trwałym faktem o rzeczy w świecie**, dokładnie symetrycznie do istniejącego `Device.capabilities` — satelita z głośnikiem stojąca w Salonie jest takim samym bytem jak żarówka. Ryzyko rozjazdu z etapu (1) nie wraca, bo capabilities nie są wpisywane ręcznie: pochodzą z handshake WS (`hello.capabilities`, dotąd wyłącznie logowane) i są podawane przy rejestracji przez UI. `WorldInterface.build()` przyjmuje więc **wyłącznie `sender_id`** — kernel przestał cokolwiek wiedzieć o kanale, czyli stał się bardziej agnostyczny, nie mniej. Zmiana celu w trakcie tury nie potrzebowała nowego mechanizmu: `speak_in_room` zwraca nowe ramowanie w treści `ToolResult`, a wyniki narzędzi i tak wracają do modelu w pętli ReAct.

- **Bramka rejestracji — jedno wejście dla każdego klienta (2026-08-22)**: Ani `POST /api/v1/chat/*` (przeglądarka), ani endpoint WS (satelita) nie sprawdzały wcześniej, czy nadawca w ogóle istnieje w World — klient mógł rozmawiać z agentem, nie będąc nigdzie widoczny. To **nie jest mechanizm bezpieczeństwa** (sieć jest zaufana, patrz "Znane luki"), tylko konsekwencja: skoro klient ma tożsamość i możliwości, musi być zatwierdzony, zanim odpali turę. REST odpowiada `403`; WS **wolno nawiązać** (inaczej nowa satelita nigdy nie trafiłaby na listę "Oczekujący" i nie dałoby się jej zatwierdzić), ale tura jest odrzucana w `VoiceSession.handle_utterance_end()` z komunikatem do satelity. Bramka jest wstrzykiwana z `main.py` jako wąski `Callable[[str], Awaitable[bool]]` — tym samym wzorcem co `connected_sender_ids`, więc **ani `voice/`, ani `network/routes/` nadal nie importują `world/`**, mimo że obie drogi wejścia korzystają z jednego źródła prawdy.

- **`Room` jako pełnoprawny byt World, niezależny od Home Assistant Areas**: Rozważano dwa warianty — (a) `Room` = surowy `area_id` HA wprost (żywa zależność od configu HA), (b) `Room` = niezależny katalog World, HA Areas wyłącznie jako podpowiedź/import. Wybrano (b), z trzech powodów: **(1)** HA nigdy nie modelowało obecności przestrzennej satelit — to nie jego odpowiedzialność, a wymuszanie tej semantyki na cudzym modelu danych jest nadużyciem; **(2)** żywa zależność od HA Areas byłaby jedynym miejscem w systemie, gdzie dane trafiają do kontekstu agenta *niejawnie* (bez świadomej deklaracji w Regis) — łamiąc zasadę opt-in konsekwentnie stosowaną od `declared_devices.json` po `Groups`; **(3)** rename/usunięcie Area w HA nie może po cichu zepsuć mapowania `SenderProfile.room_id -> sender_id`, kluczowego dla `speak_in_room`. Wygoda "nie wpisuj pokoi dwa razy" zrealizowana **jednorazowym importem** (`import_rooms_from_ha()`), nie live-syncem — po imporcie `Room` żyje własnym życiem, zmiany w HA go nie dotyczą. Przypisanie urządzenia do pokoju żyje jako pole na urządzeniu (`DeclaredDeviceEntry.room_id`), nie jako lista na `Room` — fizycznie urządzenie jest w jednym pokoju, więc pole eliminuje strukturalnie ryzyko sprzeczności, które lista wymagałaby walidować ręcznie (ten sam wybór, inny kierunek, co świadomie odwrotny `DeviceGroup.device_ids`, gdzie urządzenie *może* należeć do wielu dowolnych grup).
- **`server/voice` to peer `WorldEngine`, nie jego rozszerzenie ani konsument**: Rozważano umieszczenie pipeline'u audio/STT/TTS wewnątrz `server/world/` (satelity już tam żyły jako `SatelliteRegistration`) — odrzucone, bo World to smart home, a audio/komunikacja to inna domena; mieszanie ich zmuszałoby World do wiedzy o WebSocket/STT/TTS, czego kernel-analogiczna zasada wprost zabrania jednemu, konkretnemu silnikowi robić dla nie swojej domeny. Oba moduły znają wyłącznie opaque `sender_id` przepływający przez kernel (`AgentEngine`) — zero importu w obie strony (weryfikacja: `docs/onboarding.md`, sekcja 3). `voice` nie wpływa już w ogóle na treść promptu: framing wyprowadza World z `SenderProfile.capabilities` (patrz sekcja 5, "Modalność to capability klienta"). Rola `voice` ogranicza się do przekazania kernelowi `sender_id` i, przy handshake, zadeklarowanych możliwości klienta do wspólnego rejestru.
- **`ToolResult.redirect_sender_id` — mechaniczny hak przekierowania dostawy**: Zaprojektowany jako test poprawności granic World/voice/kernel: narzędzie `speak_in_room` (World) może przekierować **dalszą część** bieżącej odpowiedzi do innego `sender_id`, bez żadnej ze stron poznającej wiedzę drugiej. Kernel traktuje pole czysto mechanicznie (zmiana tagu publikacji `EventBus`), World nigdy nie wie o `EventBus`/WebSocket, `voice` nigdy nie czyta configu World — patrz sekcja 3.5 dla pełnego mechanizmu (rozdzielenie `session_id` od `target_client_id`).
- **VAD po stronie satelity, nie serwera**: Choć serwer i tak odbiera ciągły strumień audio (mógłby liczyć ciszę scentralizowanie), decyzję o końcu wypowiedzi (1.5s ciszy) podejmuje satelita — musi to i tak wiedzieć lokalnie, żeby przestać strumieniować/marnować pasmo, więc scentralizowanie tej jednej decyzji nie eliminowałoby potrzeby logiki po stronie satelity, tylko dodawało drugą (serwerową) bez korzyści.
- **Brak uwierzytelniania `WS /ws/voice/{sender_id}`**: Spójne z resztą systemu (opaque `sender_id` bez auth wszędzie indziej) — świadome założenie modelu zaufanej sieci lokalnej, nie przeoczenie. Do rewizji dopiero przy realnej potrzebie (np. wystawienie serwera poza LAN).
- **Filtrowanie zamienione na segregację prezentacji**: Rozważano dosłowne "pokaż tylko encje bieżącego pokoju" (z narzędziem awaryjnym do odsłaniania reszty) — odrzucone, bo opaque ID/adresowalność wymagałyby dodatkowej maszynerii (osobne pole "encje adresowalne, ale nierenderowane", eksport funkcji haszującej), a wieloetapowe wywołania narzędzi (`list_rooms`→`get_room`→akcja) zwiększają ryzyko błędu rozumowania u słabszych, lokalnych modeli (Ollama). `WorldEngine` zawsze zwraca wszystkie urządzenia w pełni adresowalne — kontekst przestrzenny to wyłącznie segregacja/nagłówki w `system_prompt`.
- **Brak rdzennego pojęcia "pokoju" (`Room`) w kernelu**: Narzucałoby kernelowi założenie „świat = dom z pokojami”, podczas gdy smart home jest tylko jedną z możliwych domen agenta. `Room` (patrz wyżej) jest pełnoprawnym bytem **World** — kernel wciąż go nie zna, zna wyłącznie opaque `sender_id`. `Device.room_id`/`SenderProfile.room_id` pozostają wyłącznie wewnętrznym słownictwem `WorldEngine`.
- **`DeviceGroup` należy do `WorldEngine`, nie do kernela**: Model grupowania jest ściśle związany z `invoke`/capability tej konkretnej domeny.
- **Usunięcie polimorfizmu Plugin/Integration (`DeviceIntegration` ABC, dynamiczna rejestracja typów)**: Wcześniejszy podział `plugins/smart_home/` + `integrations/home_assistant.py` z `register_integration_type`/`TYPE_NAME`/`SCHEMA` przygotowywał grunt pod wymienność backendu smart home. W praktyce nigdy nie pojawił się drugi, realny kandydat obok Home Assistant — HA sam jest hubem agregującym inne ekosystemy (Zigbee, Z-Wave, Matter itd.).
- **Home Assistant jako singleton, nie kolekcja połączeń**: Wcześniejszy model dopuszczał wiele nazwanych połączeń HA jednocześnie. W praktyce projekt jest jednoosobowy i prywatny z jedną instancją Home Assistant.
- **Katalog urządzeń opt-in, nie opt-out**: Nic nie jest widoczne, dopóki nie zostanie świadomie dodane przez wyszukiwarkę w UI — `declared_devices.json` jest listą *zawierającą*, jedynym źródłem prawdy o tym, co widzi agent.
- **Adresowanie po natywnym `entity_id`, nie po opaque ID ani po nazwie**: Dawne dopasowywanie po przyjaznej nazwie było kruche. Opaque ID istniało po to, żeby ukryć pochodzenie encji przy wielu, wzajemnie nieświadomych pluginach — skoro istnieje dokładnie jeden silnik świata, ryzyko kolizji/przecieku pochodzenia między pluginami nie istnieje, więc dodatkowa warstwa hashowania została świadomie porzucona (YAGNI). Do rewizji tylko z konkretnym powodem (np. potrzeba ukrycia wewnętrznego nazewnictwa HA przed LLM).
- **Brak potwierdzeń dla akcji z efektami ubocznymi**: Narzędzia wykonują się automatycznie w pętli ReAct.
- **Zapis decyzji: ta sekcja zamiast osobnych ADR-ów**: Uzasadnienia mieszkają tam, gdzie i tak czyta się architekturę. Zmieniasz jedną z powyższych decyzji? Zaktualizuj wpis, nie dopisuj nowego dokumentu obok.
- **Zasada symetrii Fakt↔narzędzie**: Każda informacja proaktywnie podana w `system_prompt` musi być **również** dostępna reaktywnie, przez narzędzie zwracające dokładnie tę samą treść (dowód: `get_time` — narzędzie i fragment `system_prompt` liczone z tego samego `datetime.now()` w jednym `build()`). Wyjątek: framing czysto instrukcyjny (np. "komunikujesz się głosem, pisz krótko") nie wymaga bliźniaczego narzędzia — nie jest wiedzą do odpytania na żądanie, tylko zawsze-obecną instrukcją.
- **World jest jedynym autorem promptu tury, kernel trzyma wyłącznie prosty fallback**: Wcześniejszy model (`ContextBuild.dynamic_context: str`, doklejany do promptu wybranego w kernelu przez `agent/prompts/` CRUD: `system_content += "\n\n" + dynamic_context`) zmuszał dwóch niepowiązanych autorów (kernel + World) do nieformalnego respektowania wspólnej hierarchii formatowania (Markdown, nagłówki) przy sklejaniu dwóch fragmentów promptu. **Zrewidowane**: `ContextBuild.system_prompt: str | None` — gdy World jest podłączony, sam dokleja swój aktywny profil tożsamości (`world/prompts.py`, `WorldPromptStore`, do 3 przełączalnych profili — jeden zawsze pusty domyślny "Profil 1") do dynamicznych faktów, zwraca **kompletny, gotowy string**. Kernel niczego nie skleja — wkleja wprost, albo (gdy `system_prompt is None`, tylko `NullWorldInterface`/testy headless) używa własnego, jednowartościowego fallbacku (`agent/prompts/`, `AgentDefaultPromptStore`, bez CRUD). Uzasadnienie filozoficzne: `agent/` to ogólny, domenowo-pusty kernel — nie powinien być *tożsamością* konkretnej instancji agenta; odcięcie World i tak redukuje agenta do zwykłego chatbota, więc utrata tożsamości razem z World nie jest wadą, tylko naturalną konsekwencją tego, czym World *jest*. **Jeśli w przyszłości pojawi się realny przypadek, w którym kernel MUSI mieć bogatą, edytowalną tożsamość niezależną od World (nie tylko fallback) — wróć do tej decyzji z konkretnym przypadkiem w ręku.**

### Zaplanowane, jeszcze niezaimplementowane

1. **Pamięć Długoterminowa i Wektorowa**: Planowana integracja modułów pamięci wektorowej i semantycznej w usłudze `server`.
2. **Fizyczni klienci satelit (ESP32/desktop)**: Klient desktopowy (Windows/Linux, `services/desktop_satellite/`, sekcja 3.7) **istnieje od dwóch sesji wstecz** — pełny cykl audio (mikrofon+głośnik) przez `sounddevice`, lokalny VAD końca wypowiedzi, lokalnie syntezowane tony wake/stop (z fallbackiem do dźwięków systemowych Windows), auto-discovery serwera. Wake-word (`OnnxWakeWordDetector`) i STT/TTS (`GroqSTTProvider`/`ElevenLabsTTSProvider`, sekcja 3.5) są dziś realne — wymagają tylko wklejenia własnych kluczy API w Web UI (zakładka Klienci, dawniej Głos). Bez klucza TTS działa łagodna degradacja do `MockTTSProvider` (cisza); bez klucza STT `STTFactory` rzuca `STTNotConfiguredError` zamiast fabrykować fałszywą transkrypcję (patrz sekcja 3.5, rewizja 2026-08-21). Firmware ESP32 (I2S mikrofon/głośnik, lokalne tony wake/stop) nadal nie istnieje. Web UI pozostaje jedynym zawsze dostępnym nadawcą tekstowym: generuje i trwale zapisuje własny opaque `sender_id` w `localStorage` (`web/js/sender_id.js`) i wysyła go z każdym `POST /api/v1/chat*`, a zakładka "Świat" pozwala zarejestrować tę przeglądarkę (albo dowolny inny `sender_id`, w tym satelitę desktopową) pod pokojem.
3. **Widoczność kroków ReAct SPRZED dołączenia do sesji już w toku**: Od rewizji "wyślij i zapomnij + `watch_session()`" (sekcja 4.1) kroki narzędzi, które wystąpią PO otwarciu kanału obserwującego, renderują się już na żywo. Nadal niewidoczne: kroki, które wystąpiły ZANIM ktoś zaczął obserwować (np. przed przeładowaniem strony w trakcie długiej pętli ReAct) — `metadata.steps` z tamtego okresu istnieje dopiero po zakończeniu całej tury, w historii.
4. **Zakładka ogólnej konfiguracji systemu**: Web UI ma dziś podział na cztery zakładki konfiguracyjne — **Dashboard** (czysty panel powitalny/statusowy, `web/js/views/dashboard.js`), **Kernel** (dostawcy LLM, `kernel_config.js`, wydzielone z dawnego Dashboardu), **Świat** (Home Assistant, pokoje, nadawcy — `views/extensions.js` montuje `HomeAssistantExtensionView` wprost, bez generycznej listy) i **Głos** (status `server/voice`, config dostawców STT/TTS + status, `voice_config.js`). Jeszcze bardziej ogólna, w pełni generyczna zakładka konfiguracji (poza tym czteroczłonowym podziałem) pozostaje wizją końcową.
