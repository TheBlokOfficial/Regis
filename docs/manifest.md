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
│   └── shared/       # Paczka shared (ConfigStore, EventBus, DTO, kodek ramek WS, ścieżki/env/sekrety, logging)
├── services/         # Niezależne usługi sieciowe
│   ├── server/       # Główna usługa serwera Regis (bramka REST/SSE, kernel, silnik świata, Web UI)
│   └── desktop_satellite/  # Klient WS satelity desktopowej (Windows/Linux) — mikrofon/głośnik
├── deploy/           # Wdrożenie produkcyjne: runbook instalacji i skrypt aktualizacji
├── docker-compose.yml # Serwer w kontenerze (sieć hosta, wolumeny na data/ i config/)
├── .env.example      # Wzorzec konfiguracji środowiskowej (katalogi, nadpisania, sekrety)
├── CHANGELOG.md      # Historia wydań
├── pyproject.toml    # Główna konfiguracja workspace, grupy dev (pytest, anyio) oraz pytest
└── README.md         # Wprowadzenie do projektu
```

### Struktura wewnętrzna usługi `services/server/src/server/`:

```text
server/
├── ports/          # KONTRAKTY dostawców AI — kernel i pipeline znają je, `ai/` je implementuje
│   ├── llm.py               # BaseLLMProvider + "język narzędzi" (ToolDefinition/ToolCallRequest/ToolResult/LLMMessage/ReasoningChunk/GenerationUsage)
│   ├── stt.py / tts.py      # BaseSTTProvider / BaseTTSProvider
│   └── wakeword.py          # WakeWordDetector (Protocol)
├── agent/          # KERNEL — "umysł" agenta, ogólny i domenowo-pusty
│   ├── engine.py            # AgentEngine — publiczne API: interact/interact_stream/start_interaction/watch_session/cancel
│   ├── turn.py              # TurnRunner (pętla ReAct, trzy wyjścia z tury) + TurnRecorder (kroki i rozumowanie)
│   ├── turn_events.py       # TurnAddress (session_id + target_client_id), TurnEventPublisher, subskrypcja zdarzeń sesji
│   ├── tasks.py             # SessionTaskRegistry — która sesja pracuje i co zdążyła napisać
│   ├── context_provider.py  # WorldInterface (Protocol) + ContextBuild + NullWorldInterface — jedyna wiedza kernela o świecie zewnętrznym
│   ├── context/             # ContextBuilder
│   ├── memory/              # MemoryManager
│   └── prompts/             # AgentDefaultPromptStore — jedna wartość, fallback bez CRUD (używany tylko gdy World milczy)
├── ai/             # KONKRETY dostawców AI — zależą wyłącznie od `ports/`
│   ├── provider_registry.py # ProviderRegistry — wspólna baza rejestrów LLM/STT/TTS (instancje + wskaźnik aktywnej)
│   ├── provider_crud.py     # ProviderCrud — wspólna logika REST-owego CRUD-u dostawców (bez znajomości HTTP)
│   ├── legacy_config.py     # Artefakt migracji jednoslotowego configu STT/TTS sprzed rejestrów
│   ├── llm/                 # OllamaProvider, OpenAICompatibleProvider, BackendRegistry, LLMRouter, model_catalog
│   ├── stt/ · tts/          # GroqSTTProvider / ElevenLabsTTSProvider + rejestry i routery
│   └── wakeword/            # OnnxWakeWordDetector + ThresholdEnergyWakeWordDetector (placeholder)
├── world/          # Jedyny, konkretny silnik świata — implementuje WorldInterface, JEDYNY autor promptu tury
│   ├── engine.py            # WorldEngine — fasada i orkiestrator: build() + CRUD delegowany do magazynów
│   ├── stores.py            # Byty jednoplikowe: config HA, zadeklarowane urządzenia, rejestr klientów
│   ├── turn_context.py      # Stan -> tekst tury (TurnFacts, lista urządzeń, różnica sekcji po przekierowaniu) — zero I/O
│   ├── prompt_sections.py   # Sekcje kontekstu tury: zamknięta lista warunków, dwie gałęzie tekstu
│   ├── prompts.py           # WorldPromptStore — do 3 przełączalnych profili tożsamości
│   ├── client.py            # HomeAssistantClient
│   ├── models.py            # Device, DeviceGroup, Room, HomeAssistantConfig, SenderProfile
│   ├── registry.py          # DeviceRegistry (magazyn na czas jednej tury)
│   ├── tools/               # home_assistant.py (urządzenia) · builtin.py (get_time, speak_in_room) · registry.py (ToolSet)
│   └── api/                 # REST po jednym pliku na rodzinę zasobów + mappers.py
├── telemetry/      # OBSERWATOR wywołań LLM — dekorator na porcie, kernel go nie zna (patrz sekcja 3.8)
│   ├── recorder.py          # RecordingLLMProvider (dekorator BaseLLMProvider) + TurnAttemptCollector
│   ├── store.py             # GenerationLogStore — SQLite, kolejka zapisu, rotacja (JEDYNA baza w projekcie)
│   └── models.py            # GenerationRecord / MessageSnapshot / AttemptSnapshot
├── voice/          # Pipeline głosowy satelit — peer WorldEngine, rozłączny (patrz sekcja 3.6)
│   ├── gateway.py           # WS endpoint /voice/{sender_id} — montaż, zdarzenia connect/disconnect, sprzątanie
│   ├── connection.py        # VoiceConnection: doręczenie, handshake, ciągła subskrypcja EventBus
│   ├── presence.py          # ClientPresenceRegistry — kto podłączony, w jakim stanie, z jakimi możliwościami
│   ├── session.py           # VoiceSession — automat stanu jednej rozmowy
│   ├── events.py            # VoiceEventType — zdarzenia satelit dla dashboardu "Klienci"
│   ├── routes.py            # Status pipeline'u, rejestr żywych połączeń, config klienta, SSE dashboardu
│   ├── provider_routes.py   # REST CRUD dostawców STT/TTS (transport nad `ai/provider_crud.py`)
│   └── dto.py               # DTO warstwy REST tej domeny
├── network/        # Bramka FastAPI i routery REST/SSE kernela
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
w `server/ports/` (`ports/llm.py`, `ports/stt.py`, `ports/tts.py`) —
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
(CRUD `.../voice/{stt,tts}/providers*`) działa **natychmiast, bez restartu
serwera** — REST-y już nie mutują `agent_engine`/`voice` z zewnątrz (wcześniej
`network/routes/providers.py` robił `agent_engine.llm_provider = ...`, co było
złamaniem hermetyzacji; STT/TTS nie miały tej mutacji wcale, stąd wymóg
restartu przed tą zmianą). `BaseSTTProvider`/`BaseTTSProvider` mają wspólną,
nieabstrakcyjną metodę `get_active_provider_class_name()` (domyślnie zwraca
własną klasę, `STTRouter`/`TTSRouter` nadpisują, zwracając nazwę rozwiązanego
konkretu) — używana przez `GET /api/v1/voice/status` do raportowania
Mock/real bez ujawniania szczegółów routingu.

### Warstwa portów (`server/ports/`) — kontrakty dostawców AI

Protokoły dostawców (`BaseLLMProvider`, `BaseSTTProvider`, `BaseTTSProvider`,
`WakeWordDetector`) mieszkają w osobnym pakiecie, między konsumentem a konkretem:

```text
    agent/  ─┐
    voice/  ─┼──> ports/ <──  ai/
    world/  ─┘
```

**Dlaczego nie u właściciela.** Do 2026-08-24 każdy protokół mieszkał u swojego
konsumenta (`agent/llm.py`, `voice/stt.py`, `voice/tts.py`), a konkrety w `ai/` —
więc `ai/` musiało importować z powrotem konsumenta. Powstały **dwa cykle między
pakietami** (`ai ↔ voice`, `agent ↔ ai`), utrzymywane przy życiu leniwymi importami
w ciałach funkcji; komentarz w `agent/engine.py` opisywał to wprost: „modułowy
import tworzył cykl, który wywracał się przy każdej kolejności importów
zaczynającej się od `server.ai`". Leniwy import przenosi błąd z czasu importu na
czas wykonania i uniemożliwia statyczną weryfikację granicy — to obejście, nie
rozwiązanie.

**Reguła przynależności**: do `ports/` trafia kontrakt, którego konkrety mieszkają
w `server.ai`. Stąd również przeniesienie detektorów wake-word do `ai/wakeword/` —
model `.onnx` jest takim samym konkretem dostawcy jak Groq czy ElevenLabs, tylko
uruchamianym lokalnie.

**`WorldInterface` ZOSTAJE w `agent/context_provider.py`** i to nie jest niekonsekwencja:
implementuje go `server.world`, a `world -> agent` jest jednokierunkowe. Żaden cykl
tam nie powstał, więc nie ma czego naprawiać — port przenosi się do `ports/` dopiero
wtedy, gdy realnie zaczyna wiązać dwie strony, nie z wyprzedzenia.

Weryfikacja (poprawny wynik każdej: brak trafień):

```bash
grep -rn "from server.voice" services/server/src/server/ai/
grep -rn "from server.agent" services/server/src/server/ai/
grep -rn "^from server.ai"   services/server/src/server/agent/
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
  - **`routes/providers.py`**: Konfiguracja i zarządzenie presetami LLM (`GET/POST/PUT/DELETE /api/v1/llm/providers/*`, schemas, `GET .../{id}/models`). `PUT /api/v1/llm/providers/{id}` edytuje istniejący preset (nazwa + opcje; typ jest niezmienny) — wcześniej zmiana `max_tokens` wymagała skasowania instancji i wklejenia klucza API od nowa. **Pole sekretne pominięte w żądaniu zachowuje obecną wartość**: frontend nigdy nie zna klucza w jawnej postaci (GET maskuje), więc nie mógłby go odesłać — bez tego każdy zapis formularza nadpisywałby klucz ciągiem kropek. Ten sam wzorzec i ta sama para funkcji (`_merge_preserving_secrets`/`_mask_secret_options`) powtórzone dla STT/TTS w `voice/provider_routes.py`.
  - **`routes/chat.py`**: Interakcje synchroniczne, strumieniowanie SSE, "wyślij i zapomnij" i anulowanie (`POST /api/v1/chat/*`) — przekazuje opaque `sender_id` z `SendChatMessageRequest` do `AgentEngine`, bez interpretacji.
  - **`routes/sessions.py`**: Zarządzanie i historia sesji konwersacji (`GET/POST/DELETE /api/v1/chat/sessions/*`) oraz kanał obserwujący sesję w czasie rzeczywistym (`GET /api/v1/chat/sessions/{id}/watch`).
  - **`routes/prompts.py`**: Fallbackowy prompt systemowy kernela, jedno pole bez CRUD (`GET/PUT /api/v1/agent/prompt`) — używany tylko gdy World nie dostarcza własnego promptu.
- **`world/api/`**: Konfiguracja Home Assistant, pokoi, urządzeń, grup, klientów, sekcji kontekstu i profili promptu — **po jednym pliku na rodzinę zasobów** (`GET/PUT /api/v1/world/config`, `/catalog`, `/declared*`, `/groups*`, `/rooms*`, `/senders*`, `/prompt-sections*`, `/prompts*`), składane przez `create_world_router()` i montowane bezpośrednio przez `network/gateway.py` pod stałym prefiksem. Router jest opcjonalny — testy chat API mogą pominąć wstrzyknięcie `world_engine` i dostać czysty kernel bez niego. Do 2026-08-24 wszystkie 28 endpointów mieszkało w jednym `world/routes.py` (394 linie).
- **Gateway (`gateway.py`)**: Serwuje wbudowaną konsolę WWW (SPA, z middleware `Cache-Control: no-cache` dla `/js/`/`/css/` — SPA bez wersjonowanych nazw plików, bez tego przeglądarki potrafią heurystycznie cache'ować JS/CSS na długo po wdrożeniu zmian), rejestruje centralny router API v1 (`create_api_router`), router `WorldEngine` pod `/api/v1/world` oraz opcjonalnie router `server.voice` (`WS /ws/voice/{sender_id}` + `GET /api/v1/voice/status`, patrz sekcja 3.5). W modelu pojedynczej usługi strumieniowanie tokenów do konsoli realizowane jest przez protokół **SSE**; dwukierunkowe **WebSockets** działają dziś dla satelit głosowych.
- **Kompozycja aplikacji**: Instancja FastAPI powstaje w `create_gateway_app()`, wołanym z asynchronicznej funkcji `main()` po inicjalizacji rejestru backendów, fallbackowego `AgentDefaultPromptStore` i `WorldEngine` (który wewnętrznie zarządza własnym `WorldPromptStore`, bez wstrzykiwania z `main.py`). Moduł `server.main` **nie eksportuje** modułowego obiektu `app`, więc uruchomienie przez `uvicorn server.main:app --reload` nie jest możliwe (patrz `docs/onboarding.md`, sekcja 4).

### 3.2 Kernel Agenta (`services/server/src/server/agent`)
- **`AgentEngine` (`engine.py`)**: Publiczne API kernela i kompozycja jego części — **sam nie prowadzi już tury**. Wystawia cztery wejścia, bo realnie istnieją cztery różne oczekiwania: `interact()` (czekam na komplet), `interact_stream()` (chcę widzieć SWOJĄ turę na żywo), `start_interaction()` (odpal i zapomnij — odbiorę gdzie indziej), `watch_session()` (chcę widzieć KAŻDĄ turę tej sesji), plus `cancel_interaction()`. Wszystkie przyjmują opaque `sender_id`.
- **`TurnRunner` (`turn.py`)**: Jedna tura od pytania do utrwalonej odpowiedzi. Realizuje **pełną pętlę agentyczną (ReAct)** — jeśli LLM zażąda wywołania narzędzia, wynik wraca do niego jako kolejna wiadomość i generacja jest kontynuowana, aż model zwróci odpowiedź finalną albo zostanie przekroczony `max_tool_iterations` (domyślnie 8). Do `MemoryManager` trafia wyłącznie finalny, skumulowany tekst. Kontekst tury budowany jest przez wstrzyknięte `context_factory`/`fallback_prompt`, nie przez bezpośrednią znajomość World — runner nie wie, że jakikolwiek silnik świata istnieje, i testuje się bez niego. **Trzy wyjścia z tury** (odpowiedź, anulowanie, błąd) są tu obok siebie, bo każde utrwala co innego.

  **Błąd tury nie jest propagowany z zadania w tle** (od 2026-08-24): w miejscu wystąpienia jest już w pełni obsłużony — pełny szczegół techniczny idzie do logów, sanityzowany komunikat do pamięci sesji i na `EventBus`, skąd odbiera go każdy zainteresowany (`interact_stream()` zamienia go z powrotem na wyjątek dla swojego wywołującego). Ponowne rzucenie służyło wyłącznie temu, że przy KAŻDEJ nieudanej turze satelity rósł w logach `Task exception was never retrieved`, opisujący problem, który system właśnie poprawnie obsłużył. `CancelledError` propagujemy dalej — bez tego zadanie nie zostanie oznaczone jako anulowane, a `cancel_interaction()` czekałoby na nie w nieskończoność.
- **`TurnRecorder` (`turn.py`)**: Chronologiczny zapis tego, co wydarzyło się w turze poza samym tekstem — kroki narzędzi (`ToolStepPayload`) i przebiegi rozumowania (`ReasoningRunPayload`). Kształt tych metadanych jest **kontraktem, nie szczegółem**: w `data/sessions/*.json` leżą realne rozmowy użytkownika, których projekt świadomie nie migruje, a Web UI odtwarza z nich całe drzewko tury.
- **`turn_events.py`**: `TurnAddress` trzyma parę `session_id` + `target_client_id` jako **jeden byt**, żeby nie dało się jej rozdzielić przez przypadek (uzasadnienie pary: sekcja 3.5). `TurnEventPublisher` dokleja oba identyfikatory do każdego zdarzenia, więc miejsce publikujące nie musi o adresowaniu pamiętać. `SessionEventSubscription` tłumaczy zdarzenia `EventBus` na `StreamEvent` — **tabelą** (`_TRANSLATIONS`), nie siedmioma prawie identycznymi domknięciami jak wcześniej; dodanie zdarzenia to jeden wiersz.
- **`SessionTaskRegistry` (`tasks.py`)**: Jedno miejsce prawdy o tym, które sesje generują odpowiedź, oraz bufor dotychczasowego tekstu. Wcześniej były to dwa równoległe słowniki w `AgentEngine`, które trzeba było pamiętać sprzątać w tym samym `finally`. Bufor czyta ktoś **z zewnątrz** tury: `GET /chat/sessions/{id}/history` dokleja go jako wiadomość częściową, gdy karta przeglądarki dołącza do sesji już generującej.
- **`context_provider.py`**: `WorldInterface` (`typing.Protocol`, jedna metoda `build(sender_id) -> ContextBuild`), `ContextBuild` (`tool_definitions`/`system_prompt`/`dispatch`) i `NullWorldInterface` (`system_prompt=None`) — **jedyna wiedza kernela o istnieniu świata zewnętrznego**. Analogia: ta sama rola co `BaseLLMProvider` względem konkretnych dostawców LLM.
- **`MemoryManager` (`memory/session.py`)**: Odpowiada za utrwalanie historii rozmów per sesja na dysku (`data/sessions/*.json`). Do `content` wiadomości trafia **wyłącznie finalny tekst odpowiedzi** — pośrednie wiadomości `assistant`/`tool` z pętli ReAct żyją tylko w pamięci na czas jednej interakcji, a rozumowanie modelu ląduje obok, w `metadata.reasoning` (`ReasoningRunPayload`: `seq`/`text_offset`/`content`, mirror `metadata.steps`). Podział ma konkretny cel: `content` jest odsyłany modelowi jako historia w każdej kolejnej turze i czytany na głos przez TTS, więc chain of thought w tym polu kosztował tokeny i psuł mowę (sekcja 5, "Reasoning rozdzielony strukturalnie").
  **Dwie reguły przeciw nieskończonemu narastaniu historii (2026-08-30)** mieszkają tutaj, a nie u wywołującego, bo obowiązują każdego klienta kernela, nie jedną bramkę:
  - **wygaszanie po bezczynności** — `Session.idle_ttl_seconds`, sprawdzane **leniwie**, przy następnym sięgnięciu po sesję (`get_or_create_session`). Bez timera i bez wątku w tle, bo `updated_at` niesie już całą potrzebną informację (ten sam wzorzec co leniwa rotacja telemetrii, sekcja 3.8). Czyszczona jest wyłącznie **historia** — ID, tytuł i `created_at` zostają, bo satelita jest rozpoznawana po `session_id` równym swojemu `sender_id` i rotacja identyfikatora zerwałaby jej tożsamość w rejestrze klientów. Powód istnienia reguły: satelita używa jednego `session_id` przez cały czas swojego istnienia, więc bez limitu model dostawał `max_history_messages` wiadomości sprzed wielu godzin jako „bieżącą rozmowę";
  - **sufit liczby utrwalanych wiadomości** — `max_persisted_messages` (domyślnie 200), przycinany przy każdym dopisaniu; dotyczy też sesji bez TTL-a, więc chroni plik na dysku również tam, gdzie historia ma żyć długo. Świadoma strata: najstarsze wiadomości znikają nieodwracalnie, także z widoku w Web UI.

  **Politykę wnosi brzeg kompozycji, nie kernel.** `AgentEngine.start_interaction()`/`interact_stream()` przyjmują opcjonalne `session_idle_ttl_seconds`; podaje je `voice/connection.py` (z `Settings.satellite_session_idle_ttl_seconds`), a `network/routes/chat.py` nie podaje nic — czat Web UI ma własną listę sesji i nie wygasa. Kernel nie wie, że rozmawia z satelitą. Reguły są niezależne od `ContextBuilder.max_history_messages`, który przycina to, co idzie do modelu; tu chodzi o rozmiar i świeżość samej pamięci.
- **`ContextBuilder` (`context/builder.py`)**: Komponuje ostateczny prompt dla LLM, łącząc instrukcje systemowe z historią sesji. Przycina historię do `max_history_messages` najnowszych wiadomości (domyślnie 40, konfigurowalne w `settings.json`), by uniknąć przekroczenia limitu kontekstu modelu w długich konwersacjach. Przycinanie działa na podstawie liczby wiadomości, nie realnego zliczania tokenów. Parametr `tools_available` warunkowo dokleja jedno neutralne zdanie o dostępności narzędzi — nigdy nie wymienia ich nazw ani pochodzenia. Parametr `system_prompt` (już gotowy string — wkład World albo fallback kernela) jest wklejany wprost jako treść systemowa, bez żadnego dalszego sklejania czy formatowania po stronie kernela.
- **`AgentDefaultPromptStore` (`prompts/store.py`)**: Jedna wartość (`data/agent_default_prompt.json`), bez CRUD — fallback używany **wyłącznie** gdy `ContextBuild.system_prompt is None` (brak World albo `NullWorldInterface`, np. testy headless / przenośność kernela). Przy pierwszym uruchomieniu bez pliku próbuje best-effort migracji z dawnego legacy `data/prompts/*.json`+`active_prompt.json`; w przeciwnym razie zasiewa `DEFAULT_SYSTEM_PROMPT`. Właściwy, edytowalny CRUD tożsamości (do 3 przełączalnych profili) żyje dziś w `world/prompts.py` — World jest jedynym autorem promptu, gdy jest podłączony (patrz sekcja 3.4, sekcja 5).

### 3.3 Protokół LLM (`services/server/src/server/ports/llm.py`) i konkrety (`server/ai/llm`)
- **`BaseLLMProvider` (`ports/llm.py`)**: Interfejs abstrakcyjny definiujący metodę `generate_stream(messages, tools)`, która yielduje `str` (fragment **tekstu odpowiedzi**), `ReasoningChunk` (fragment rozumowania modelu), `ToolCallRequest` (kompletne żądanie wywołania narzędzia) **albo** `GenerationUsage` (terminalne rozliczenie generacji). Cała złożoność formatu API konkretnego dostawcy (OpenRouter: akumulacja fragmentarycznych `delta.tool_calls` z SSE; Ollama: kompletne `tool_calls` w jednym komunikacie) jest ukryta wewnątrz providera — kernel operuje wyłącznie na abstrakcyjnych typach. Mieszka w `ports/`, między kernelem a konkretami z `server/ai/llm/` — patrz sekcja "Warstwa portów" wyżej.
- **`ToolDefinition` / `ToolCallRequest` / `ToolResult` (`ports/llm.py`)**: Typy definiujące, **czym jest narzędzie** w całym systemie.
- **`ReasoningChunk` (`ports/llm.py`, 2026-08-23)**: Rozumowanie modelu (chain of thought) jest **osobnym typem zdarzenia**, nie stringiem ze znacznikiem `<think>…</think>` w treści. Uzasadnienie i skutki dawnego modelu: sekcja 5, "Reasoning rozdzielony strukturalnie". Providerzy (`ai/llm/providers/*`) czytają go z `delta.reasoning`/`reasoning_content`/`thinking` i yielduje go jako `ReasoningChunk`; kto nie potrafi go wyświetlić, po prostu pomija ten typ — `isinstance(event, str)` nadal jednoznacznie znaczy "tekst odpowiedzi" (dzięki czemu `BaseLLMProvider.generate()` filtruje rozumowanie za darmo).
- **`GenerationUsage` (`ports/llm.py`, 2026-08-25)**: Rozliczenie zakończonej generacji — liczniki tokenów (`prompt`/`completion`/`cached`), `finish_reason` i model, który realnie odpowiedział. Emitowane **raz, jako ostatnie zdarzenie strumienia**; nie jest fragmentem, stąd brak sufiksu `...Chunk`, ale powód istnienia jest ten sam co przy `ReasoningChunk`: fakt strukturalny podróżuje jako osobny typ, a nie doklejony do tekstu ani odczytywany po fakcie z prywatnego stanu providera. Każde pole jest `| None`, bo **żaden dostawca nie daje kompletu** — `cached_tokens` zwraca dziś tylko OpenRouter, Ollama ma `done_reason` zamiast `finish_reason`, a starsze bramki OpenAI-compatible potrafią pominąć blok `usage` w całości; `None` znaczy „dostawca tego nie powiedział" i nigdy nie jest zastępowane zerem. Odblokowanie tych danych wymagało realnych zmian w obu konkretach: `stream_options: {"include_usage": true}` w payloadzie (opt-in w całej rodzinie OpenAI-compatible), odczyt `usage` z chunka o PUSTEJ liście `choices` (poprzedni parser czytał tylko wewnątrz `if choices` i kończył na `[DONE]`) oraz `prompt_eval_count`/`eval_count`/`done_reason` z finalnego komunikatu Ollamy. **`TurnRunner._stream_one_round` musi mieć na ten typ jawną gałąź `isinstance`** — jego `else` traktuje wszystko nieznane jak tekst odpowiedzi, więc nowe zdarzenie bez tej gałęzi trafiłoby do pamięci sesji i z powrotem do modelu. Konsekwencja gratis: `TokenBudgetTracker` bramkuje na realnym zużyciu, a estymata `len/4` została awaryjnym marginesem i jedynym oszacowaniem *przed* wywołaniem.
- **`OllamaProvider` / `OpenAICompatibleProvider` (`ai/llm/providers/`)**: Konkretne implementacje `BaseLLMProvider`. Obie wspierają tool calling. `OpenAICompatibleProvider` (scalone 2026-08-21 — wcześniej dwie niemal identyczne klasy `OpenRouterProvider`/`GroqProvider`) obsługuje **dwa** `ProviderType` naraz: `OPENROUTER` i `GROQ` — to jeden konkret REST OpenAI-compatible, parametryzowany przez `base_url`/`extra_headers`/`extra_payload` (konstruowany różnie per typ w `LLMFactory.create_provider()`, patrz niżej). `ProviderType`/schemat/badge na karcie **zostają rozdzielone** mimo scalonej implementacji — to dwa różne konta/klucze API z perspektywy użytkownika, więc dropdown i identyfikacja instancji (`p.type`) muszą pozostać osobne; scalenie dotyczy wyłącznie kodu, nie UI. Endpoint Groq: `https://api.groq.com/openai/v1/chat/completions` (kontrakt zweryfikowany w dokumentacji Groq, nie zgadywany), format SSE/tool_calls identyczny jak OpenRouter. OpenRouter dokłada `extra_payload={"reasoning": {"effort": "none"}}` i `extra_headers={"HTTP-Referer": ..., "X-Title": ...}` — rozszerzenia specyficzne dla OpenRouter, nieudokumentowane w API Groq, więc Groq ich nie dostaje. `base_url` **nie** jest polem formularza dla OPENROUTER/GROQ (zaszyty na sztywno w fabryce) — w odróżnieniu od Ollamy, gdzie jest edytowalny (self-hosted, zmienny).
- **`LLMFactory` (`ai/llm/factory.py`)**: Tworzy instancję providera z `BackendInstanceConfig` i **mapuje opcje presetu na payload konkretnego dostawcy** — te same pojęcia mają u każdego inną nazwę i inne zagnieżdżenie (OpenRouter: `reasoning: {"effort": …}`; Groq: płaskie `reasoning_effort`/`include_reasoning`; Ollama: worek `options` + `think`). Puste pole znaczy "nie wysyłaj tego parametru w ogóle", nie "wyślij zero".
- **`model_catalog.py` (`ai/llm/`, 2026-08-23)**: Skąd wziąć listę modeli i **jakie parametry rozumie konkretny model**. Trzy dostawcy, trzy różne źródła prawdy (świadomy wybór, nie niespójność): OpenRouter sam podaje `supported_parameters` per model w publicznym `GET /api/v1/models`, więc formularz powstaje wprost z tego i nie gnije; Groq daje listę modeli (`/openai/v1/models`), ale parametry biorą się z tabeli rodzin w tym pliku (Groq ich nie eksponuje, a jest ich garść i są udokumentowane); Ollama daje `/api/tags`, czyli modele REALNIE pobrane na tej maszynie, plus tabela podpowiedzi per rodzina (`think` dla qwen3/deepseek-r1/gpt-oss). **Lista nigdy nie zamyka wyboru** — każdy typ pozwala wpisać identyfikator z ręki (`fallback_options_schema`), bo nowy model pojawia się u dostawcy wcześniej, niż ktokolwiek zaktualizuje ten plik. Brak klucza/padnięty serwer to **nie błąd**, tylko `detail` w odpowiedzi 200 — UI pokazuje powód zamiast udawać, że dostawca nie ma modeli.
- **`BackendRegistry` (`ai/llm/registry.py`)**: Dynamiczny rejestr dostawców modeli (pliki JSON w `data/backends/`) z możliwością płynnego przełączania aktywnego backendu (np. z lokalnego `OllamaProvider` na chmurowy `OpenAICompatibleProvider` — OpenRouter albo Groq).

- **Łańcuch fallbacku LLM — `TokenBudgetTracker` + `CircuitBreaker` + `LLMRouter` (2026-08-25)**: Zbudowane po realnym, powtarzalnym incydencie (Groq TPM 8000/min na `openai/gpt-oss-120b`, HTTP 429 `rate_limit_exceeded` — zaobserwowane wielokrotnie w `data/logs/`), nie spekulacyjnie. Kernel wymaga natychmiastowej reakcji (sterowanie głosowe w czasie rzeczywistym), więc klasyczny retry-z-backoffem odpadał — router **wybiera** kandydata przed startem, nie czeka i próbuje ponownie.
  - **Aktywny preset (`active_id`) jest zawsze Priorytetem 0** — próbowany pierwszy niezależnie od zawartości łańcucha; `BackendRegistry.get_fallback_chain()`/`set_fallback_chain()` (plik `data/fallback_chain.json`, osobny od `active_backend.json` — te dwa pojęcia się nie zlewają) dokłada wyłącznie kolejne poziomy, z deduplikacją aktywnego, gdyby się tam znalazł. Pusty łańcuch = zachowanie nierozróżnialne od stanu sprzed jego wprowadzenia.
  - **Zasada bezpieczeństwa przełączania**: zamiana na kolejnego kandydata jest dopuszczalna WYŁĄCZNIE, dopóki bieżący nie wyemitował jeszcze żadnego zdarzenia strumienia — zweryfikowane w kodzie `openai_compatible.py`, że błąd HTTP (w tym 429) jest rzucany zaraz po nagłówkach, przed pierwszą iteracją SSE, więc to przełączenie jest zawsze bezpieczne dla tej klasy błędów. Po pierwszym `yield` błąd propaguje normalnie — cicha zamiana w środku odpowiedzi ucinałaby/duplikowała tekst już oddany do TTS.
  - **`TokenBudgetTracker`** (`ai/llm/token_budget.py`) — opcjonalna, lokalna, procesowa (nie przetrwa restartu) estymacja zużycia tokenów w oknie 60s per preset, oparta na `tpm_limit` w `options` presetu (pole opcjonalne — brak wyłącza sprawdzanie). **`CircuitBreaker`** (`ai/llm/circuit_breaker.py`) — realna siatka bezpieczeństwa: po złapanym błędzie przed pierwszym `yield` parsuje sugerowany czas oczekiwania z treści (Groq zwraca dosłownie „Please try again in Xs") i pomija tego kandydata w kolejnych turach do wygaśnięcia cooldownu.
  - **UI scalone z listą presetów, nie osobny panel** (rewizja tej samej sesji, po iteracji z użytkownikiem) — pole `Priority` żyje bezpośrednio w nagłówku karty presetu (`components/provider_crud_section.js`, generyczne dla LLM/STT/TTS, ale włączone tylko dla LLM przez `api.getFallbackChain`/`setFallbackChain`); aktywny preset w ogóle nie renderuje tego pola (jest Priorytetem 0 z definicji aktywacji). Pierwsza wersja (osobna sekcja `LlmFallbackChainSection` z checkboxami + strzałkami) została w pełni zastąpiona i usunięta w tej samej sesji.
  - **Bugfix na żywo**: `BackendRegistry.delete_instance()` musiał dostać override czyszczący usuwany ID z zapisanego łańcucha — bez tego martwy ID zostawał w `fallback_chain.json` na zawsze, a `set_fallback_chain` odrzuca CAŁY zapis przy choć jednym nieznanym ID, więc edycja priorytetu zupełnie innego, nietkniętego presetu psuła się z pozoru losowo. Frontend dostał tę samą obronę (filtr po aktualnie znanych ID przy ładowaniu) jako drugą warstwę.

### 3.4 WorldEngine (`services/server/src/server/world`)

Jedyny, konkretny silnik świata — implementuje `WorldInterface` strukturalnie
(bez importu z `agent/`). Wewnątrz: klient Home Assistant, magazyny plikowe,
narzędzia — zwykłe, wprost wołane obiekty Pythona, zero protokołu między nimi.

`WorldEngine` jest dziś **fasadą i orkiestratorem**; rzeczy, które robi, mieszkają
osobno i dają się sprawdzić bez niego. Do 2026-08-24 była to jedna klasa na 734
linie z siedmioma odpowiedzialnościami, w której sam `build()` miał 152 linie —
żeby dodać jedno narzędzie, trzeba było wejść w środek funkcji budującej prompt.

| Moduł | Odpowiedzialność | I/O |
| :--- | :--- | :--- |
| `stores.py` | byty jednoplikowe: config HA, zadeklarowane urządzenia, rejestr klientów | dysk |
| `shared.JsonInstanceRepository` | kolekcje „plik na instancję": pokoje, grupy, profile promptu | dysk |
| `turn_context.py` | stan → tekst tury: `TurnFacts`, lista urządzeń, różnica sekcji po przekierowaniu | **brak** |
| `prompt_sections.py` | edytowalne sekcje kontekstu, zamknięta lista warunków | dysk (config) |
| `tools/` | narzędzia agenta: definicje + wykonanie + routing wywołań | sieć (HA) |
| `api/` | REST, po jednym pliku na rodzinę zasobów | HTTP |
| `engine.py` | złożenie powyższych w `ContextBuild` jednej tury | — |

- **`WorldEngine` (`engine.py`)**: Konfiguracja Home Assistant (singleton, jeden `base_url`/`access_token`), zadeklarowana lista urządzeń (opt-in), grupy, pokoje, przypisania klientów do pokoi i profile promptu — wszystko jako pliki JSON pod `data/world/` (`config.json`, `declared_devices.json`, `groups/*.json`, `rooms/*.json`, `senders.json`, `prompts/*.json`+`active_prompt.json`). Metody CRUD są cienkimi fasadami nad magazynami; własną logikę mają tylko tam, gdzie istnieje reguła domenowa (np. `upsert_sender()` — patrz niżej).

  `build(sender_id)` czyta w ustalonej kolejności: profil klienta (gdzie stoi, co potrafi) **przed** Home Assistantem, żeby niedostępność HA nigdy nie ucięła ramowania dostawy; potem urządzenia i grupy; potem `turn_context.build_turn_facts()` składa `TurnFacts`, a `render_turn_context()` przepuszcza je przez sekcje użytkownika. Tożsamość (aktywny profil promptu) idzie osobno, do `system_prompt`. Narzędzia składa `ToolSet` — kernel dostaje listę definicji i jedną funkcję `dispatch`, nie wiedząc, że część z nich obsługuje egzekutor Home Assistanta, a część funkcje własne Świata. Adresowanie idzie wprost natywnym `entity_id`, **bez pośredniej warstwy opaque ID**: skoro istnieje dokładnie jeden silnik, nie ma ryzyka kolizji identyfikatorów, więc nie ma po co ich ukrywać.

  Ramowanie dostawy wyprowadzane jest z `SenderProfile.capabilities` (`ClientCapability.MIC/SPEAKER/TEXT`) — obecność `SPEAKER` decyduje, którą gałąź sekcji wstawić. Zastąpiło to dawny parametr `voice_mode: bool` (sekcja 5, "Modalność to capability klienta").

  **`upsert_sender()`** trzyma regułę „pominięte pole zachowuje obecną wartość": `capabilities` i `display_name` tak (pusty string czyści nazwę jawnie), `room_id` **nie** — tam `None` to legalne „brak pokoju" z pickera. Reguła jest w silniku, a nie w routerze REST, bo obowiązuje każdego wywołującego i daje się przetestować bez podnoszenia HTTP; jedno wywołanie obsługuje trzy miejsca UI o różnej wiedzy o kliencie.
- **`ToolSet` (`tools/registry.py`)**: Narzędzie to para **definicja + handler** (`Tool`); `ToolSet` składa je w listę definicji dla modelu i jedną funkcję `dispatch` dla kernela. Urządzenia Home Assistant idą przez `executor`, a nie przez wpisy w słowniku — ich nazwy są stałe, a routing po `entity_id` (urządzenie/grupa/tablica) jest już zamknięty wewnątrz egzekutora.

  Do egzekutora trafiają **wyłącznie nazwy faktycznie zadeklarowane**. Wcześniej dostawał wszystko, czego nie znalazł słownik, więc halucynowana nazwa narzędzia wracała do modelu jako „Nie znaleziono żadnej pasującej encji" — komunikat kierujący go na poprawianie `entity_id` zamiast na to, że takiego narzędzia po prostu nie ma.

  To **nie jest** powrót do porzuconej wielorozszerzeniowości (sekcja 5): nie ma protokołu między niezależnymi rozszerzeniami, rejestracji typów ani przełącznika enable/disable — to zwykły słownik nazwa → funkcja wewnątrz jednego silnika.
- **`turn_context.py`**: Wszystkie funkcje są **czyste** — dostają gotowe dane i zwracają stringi, zero I/O. Dzięki temu format wiersza urządzenia, segregacja po pokojach czy różnica sekcji po przekierowaniu (`sections_gained_after_redirect`) testują się bez dysku, sieci i bez podnoszenia silnika.
- **`WorldPromptStore` (`prompts.py`)**: CRUD do **3** przełączalnych profili tożsamości (`list_all`/`get`/`create`/`update`/`delete`/`set_active`/`get_active_content`) — dosłownie dawny, wieloprofilowy `PromptStore` z `agent/prompts/`, przeniesiony do World razem z odpowiedzialnością za tożsamość agenta. `create()` rzuca `ValueError` przy próbie utworzenia 4. profilu. Domyślnie zawsze istnieje **"Profil 1"** z pustą treścią (World nie dziedziczy tożsamości po kernelu) — pusty aktywny profil oznacza "brak persony, tylko dynamiczne fakty", nie błąd.
- **Katalog opt-in**: `DeclaredDeviceEntry` (`display_name`, `room_id`) per natywny `entity_id`, plik `declared_devices.json`. Model jest **opt-in** — brak wpisu oznacza niewidoczność, niezależnie od tego, czy encja istnieje po stronie HA. `resolve_devices()` iteruje po zadeklarowanych wpisach i dociąga (join po `entity_id`) aktualny stan z surowego katalogu HA (`get_catalog()`), kopiując `room_id` z deklaracji na budowany `Device`.
- **`Room` (`models.py`) — pełnoprawny byt World, niezależny od Home Assistant Areas**: `{id, name}`, CRUD (`create_room`/`list_rooms`/`update_room`/`delete_room`) będący dokładnym mirrorem `DeviceGroup`. `Device.area` (surowy `area_id` HA) pozostaje wyłącznie **podpowiedzią** w surowym katalogu (`GET /world/catalog`) — nigdy prawdą o pokoju; `WorldEngine.import_rooms_from_ha()` to jawna, **jednorazowa** akcja tworząca `Room` per unikalna, niepusta HA Area jeszcze nieobecna wśród istniejących pokoi (dopasowanie po nazwie, bez rozróżniania wielkości liter) — nie ciągła synchronizacja. Uzasadnienie pełne w sekcji 5.
- **`Device` / `DeviceGroup` / `SenderProfile` (`models.py`)**: `Device.id` to wprost natywny `entity_id` Home Assistant (singleton — bez przestrzeni nazw połączenia). `Device.capabilities` to mapa nazwa narzędzia → granularne cechy (`dict[str, frozenset[str]]`). `Device.room_id` (kopiowane z `DeclaredDeviceEntry.room_id`) to **jedyne** źródło pojęcia "pokój" w systemie, nadal nieobecne w kernelu (patrz sekcja 5). `SenderProfile` (`display_name`/`room_id`/`capabilities`, **bez** kanału komunikacji ani tożsamości urządzenia — to wiedza `server/voice`, patrz sekcja 3.5) mapuje opaque `sender_id` na `Room` — zgodność `room_id` z rzeczywistym rozmieszczeniem satelity jest odpowiedzialnością **konfiguracyjną** (administrator rejestrujący nadawcę), nie kodową. `display_name` (2026-08-23) to czysto ludzka etykieta, dokładny mirror `DeclaredDeviceEntry.display_name` — klient stojący w pokoju jest takim samym bytem World co żarówka. Nie jest generowana automatycznie (pusta = UI pokazuje skrócony `sender_id`) i **nie służy do adresowania**: `speak_in_room` nadal rozwiązuje odbiorcę przez pokój, nigdy przez nazwę (patrz sekcja 5, "Adresowanie po natywnym `entity_id`, nie po opaque ID ani po nazwie"). Nadaje się ją wyłącznie w zakładce Klienci; Świat pokazuje ją read-only.
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

  Bufor mowy zbiera **wyłącznie** fragmenty oznaczone `kind: "answer"` — rozumowanie
  modelu płynie tym samym kanałem (`CHAT_CHUNK`), ale z `kind: "reasoning"` i jest tu
  pomijane (sekcja 5, "Reasoning rozdzielony strukturalnie"). Samą syntezę odpala
  `_start_speaking()` jako **zadanie w tle**, nie `await` wewnątrz handlera: `EventBus`
  woła handlery sekwencyjnie i czeka na każdy, więc synteza w handlerze blokowała
  publikację `CHAT_DONE` do wszystkich pozostałych subskrybentów (m.in. kanału SSE
  Web UI) na cały czas trwania TTS.
- **`ToolResult.redirect_sender_id`** (`ports/llm.py`): mechaniczne pole — kernel nie interpretuje jego znaczenia, tylko zmienia **`target_client_id`** (adres dostawy) na resztę tury (`agent/turn.py`, `TurnRunner._execute_tool`; para identyfikatorów żyje w `TurnAddress`, `agent/turn_events.py`). Każde zdarzenie `CHAT_*`/`TOOL_CALL_*` niesie **dwa niezależne identyfikatory**: `session_id` (tożsamość rozmowy/pamięci — **nigdy się nie zmienia**, filtrują po nim `watch_session`/`interact_stream`/Web UI) oraz `target_client_id` (adres dostawy — filtrują po nim odbiorcy fizyczni, `voice/gateway.py`). Historia (`MemoryManager`) zawsze pod oryginalnym `session_id` — przekierowanie zmienia wyłącznie dostawę, nigdy właściciela konwersacji.

  **Rewizja (2026-08-22)**: wcześniej obie role pełniło jedno pole `session_id` (`effective_session_id`), co działało wyłącznie dzięki temu, że dla satelit `session_id == sender_id`. Dla klienta, u którego te wartości się różnią (przeglądarka: sesja czatu vs `sender_id` z localStorage), przekierowanie publikowało zdarzenia pod tagiem, którego nikt nie słuchał — **odpowiedź znikała bez błędu**. Rozdzielenie usunęło też potrzebę dawnego dual-castu zdarzeń terminalnych (istniał tylko po to, by `interact_stream()` nie zawisł, gdy tag dostawy uciekł). `voice/gateway.py::_on_done` obsługuje dziś jawnie obie role: adresat mówi zgromadzony tekst, a inicjator, któremu turę dostarczono gdzie indziej, wraca do nasłuchu zamiast zostać w `PROCESSING`.
- **`VoiceSession`** (`voice/session.py`): czysty automat stanu treści (`LISTENING_WAKEWORD` → `RECORDING_UTTERANCE` → `PROCESSING` → `SYNTHESIZING` → `SPEAKING` → z powrotem), zero wiedzy o WebSocket/EventBus — testowalny w izolacji (`tests/test_voice_pipeline.py`). `reset_to_listening()` to awaryjny powrót do nasłuchu wołany przez gateway po `CHAT_ERROR`/`CHAT_CANCELLED`, żeby sesja nigdy nie utknęła w `PROCESSING`/`SPEAKING` na zawsze — **resetuje stan wyłącznie po stronie serwera**, więc każdy wywołujący musi wcześniej wysłać satelicie `TURN_END`/`ERROR` (satelita, `desktop_satellite/session.py::handle_server_frame`, wraca do nasłuchu i wznawia mikrofon wyłącznie po jednej z tych ramek — bez niej zostaje uwięziona w `PROCESSING` na stałe, mimo że serwer już myśli, że wrócił do nasłuchu; żywy bug znaleziony 2026-08-25 przy pierwszej wersji bramki niżej, poprawiony przez użycie `end_turn_without_speech()`). `handle_utterance_end()` odrzuca cicho (przez `end_turn_without_speech()`, nie gołe `reset_to_listening()`) nagrania, których szczytowa amplituda (`shared.peak_amplitude`) nigdy nie przekroczyła `Settings.vad_amplitude_threshold` — ten sam próg, którym satelita mierzy własną ciszę — zanim trafią do STT: przypadkowe wyzwolenie wake-worda dawało czyste audio ciszy/szumu, na którym Groq/Whisper halucynował pojedyncze słowa ("Dzięki", "Okej"), odpalając zbędną turę agenta. Czas trwania nagrania **nie** jest tu sygnałem (próbowany i odrzucony wariant) — satelita zawsze czeka pełne `vad_silence_duration_ms` ciszy przed końcem nagrywania (`desktop_satellite/vad.py`, sekcja 3.7), więc nawet pusta wypowiedź ma ten sam ~1.5 s ogon co realna, krótka mowa.

  **Zasada nadrzędna tego automatu (utrwalona po sesji 2026-08-23, w której złamały ją naraz trzy różne ścieżki)**: satelita wstrzymuje mikrofon poza nasłuchem, więc **każde** wyjście z `PROCESSING`/`SYNTHESIZING`/`SPEAKING` musi kończyć się powrotem do `LISTENING_WAKEWORD` — stan bez wyjścia to nie "zawieszenie na chwilę", tylko trwała głuchota klienta do restartu. Trzy załatane wtedy dziury: (1) tura bez tekstu do wypowiedzenia kończyła się w `gateway.py::_on_done` gołym `return` (dziś: `end_turn_without_speech()` → ramka `turn_end`); (2) wyjątek dostawcy TTS w `speak()` nie był łapany, a `EventBus.publish()` połyka wyjątki handlerów, więc błąd nie miał jak nigdzie wypłynąć (dziś: `try/except` → `send_error` + powrót do nasłuchu); (3) puste audio ze skądinąd udanej syntezy szło na satelitę jako `tts_start`/`tts_end` bez treści.

  **`SYNTHESIZING` jest osobnym stanem od `SPEAKING`**, bo to dwa różne oczekiwania: pierwsze trwa tyle, ile zapytanie do dostawcy TTS, drugie tyle, ile realne odtwarzanie u klienta. Dopóki oba nazywały się `SPEAKING`, dashboard "Klienci" pokazywał "Odpowiada" także wtedy, gdy nic jeszcze nie grało — i nie dało się odróżnić wolnej syntezy od zawieszonego odtwarzania.
- **Protokół WS** (`shared/voice_protocol.py` — **od tej sesji w `packages/shared`, nie w `server/voice/`**: kontrakt ramek, współdzielony przez dwie niezależne usługi, `server` i `desktop_satellite`, patrz sekcja 3.6): ramki binarne = surowe PCM16 mono (bez kodeka) w obie strony; ramki tekstowe JSON = control-plane (`hello`/`utterance_end`/`playback_done` od satelity, `wake_detected`/`play_stop_tone`/`tts_start`/`tts_end`/`turn_end`/`error`/`client_config` od serwera). `turn_end` (2026-08-23) kończy turę, która nie wyprodukowała nic do wypowiedzenia — świadomie osobna od `error`, bo nic się nie zepsuło; bez niej satelita czekała na `tts_start`, który nigdy nie przychodził. Dźwięki wake/stop-tone są lokalne (wypalone w firmware satelity/generowane przez klienta desktopowego), nigdy strumieniowane z serwera.
- **VAD po stronie satelity**: to satelita (nie serwer) decyduje o końcu wypowiedzi (min. 1.5s ciszy) i wysyła `utterance_end` — świadoma decyzja architektoniczna (satelita i tak musi wiedzieć, kiedy przestać nagrywać/streamować, żeby nie wysyłać ciszy w nieskończoność).
- **STT/TTS** — protokół (`ports/stt.py`::`BaseSTTProvider`, `ports/tts.py`::`BaseTTSProvider`) to mirror `BaseLLMProvider` (`ports/llm.py`); od 2026-08-24 wszystkie trzy mieszkają w `server/ports/` (patrz sekcja "Warstwa portów"). `BaseTTSProvider.synthesize_stream()` jest prymitywem (kolejny mirror: `generate_stream`/`generate`) od 2026-08-24 — `synthesize()` zbiera strumień w jeden bufor, patrz sekcja 5, "TTS strumieniowany, nie sklejany w jeden bufor". Od 2026-08-21 (sesja: parytet CRUD z LLM) `server/ai/stt`/`server/ai/tts` mają **pełny rejestr wielu nazwanych instancji**, mirror `ai/llm/registry.py`::`BackendRegistry` (od 2026-08-24 wszystkie trzy to cienkie specjalizacje wspólnego `ai/provider_registry.py`::`ProviderRegistry`) — `STTRegistry`/`TTSRegistry` (pliki `data/stt_backends/*.json`+`data/active_stt_backend.json`, `data/tts_backends/*.json`+`data/active_tts_backend.json`), `STTFactory`/`TTSFactory` (`create_provider`+`get_all_schemas()`, Single Source of Truth schematów, mirror `LLMFactory`). Konkrety: `GroqSTTProvider` (`ai/stt/providers.py`, `AsyncGroq.audio.transcriptions.create()`, modele `whisper-large-v3-turbo`/`whisper-large-v3`, `language="pl"` — surowe PCM16 owijane w minimalny nagłówek WAV, `_pcm_to_wav()`, bo Groq przyjmuje pliki audio, nie goły strumień) i `ElevenLabsTTSProvider` (`ai/tts/providers.py`, `AsyncElevenLabs.text_to_speech.convert()`, `output_format="pcm_16000"` — **dokładnie** nasz format przewodowy, zero resamplingu; `model_id="eleven_multilingual_v2"`, jedyny model jawnie potwierdzony jako wspierający polski). Puste `api_key` w opcjach instancji TTS = łagodna degradacja do `MockTTSProvider` (cisza proporcjonalna do długości tekstu — nieszkodliwy fallback). **STT jest asymetryczne** (rewizja z 2026-08-21, po sesji testowej end-to-end): pusty `api_key` w `STTFactory.create_provider` rzuca `STTNotConfiguredError` zamiast po cichu zwracać `MockSTTProvider` — satelita nagrywa realną mowę, więc podstawienie sfabrykowanego tekstu ("Testowa wiadomość głosowa.") wygenerowałoby prawdziwą turę agenta na podstawie czegoś, czego użytkownik nigdy nie powiedział (mylące w przeciwieństwie do jawnie fałszywej odpowiedzi Mock LLM/ciszy Mock TTS). `VoiceSession.handle_utterance_end()` łapie ten wyjątek, wysyła `error` do satelity (`SatelliteLink.send_error()`, nowa metoda protokołu, reużyta też przez `gateway.py::_on_error_or_cancelled`) i wraca do nasłuchu — **bez** wywołania `on_transcript`/`AgentEngine.start_interaction()`. `MockSTTProvider` zostaje w kodzie wyłącznie jako jawny wybór w testach jednostkowych, bez osobnego przełącznika `enabled`.

  REST: `voice/provider_routes.py`::`create_voice_providers_router` — pełny CRUD mirror `network/routes/providers.py` (LLM): `GET .../stt/providers/schemas`, `GET/POST/PUT .../stt/providers[/active]`, `DELETE .../stt/providers/{id}` i analogicznie `.../tts/providers*`. Powód: użytkownik planuje lokalne rozwiązania STT/TTS obok Groq/ElevenLabs — konkretny drugi kandydat w ręku, warunek YAGNI-out spełniony (w odróżnieniu od wcześniejszej sesji, gdzie jeden realny dostawca każdego typu uzasadniał tylko płaski, jednosslotowy config). Płaski shim `GET/PUT /api/v1/voice/providers/config`, który przez jedną sesję utrzymywał stary kontrakt `voice_config.js`, **został usunięty (2026-08-22)** — po przenosinach configu do zakładki Dostawcy nie miał już ani jednego konsumenta. Pierwsze uruchomienie po wprowadzeniu rejestrów: best-effort migracja z legacy `data/voice/config.json` (`VoiceProvidersConfig`) do jednej domyślnej instancji per typ (`stt_groq_default`/`tts_elevenlabs_default`) — istniejące klucze API użytkownika nie giną.

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

**Rejestr obecności klienta (`voice/presence.py`, 2026-08-30)** — `ClientPresenceRegistry`
odpowiada na trzy pytania o żywe połączenia: kto jest podłączony (panel „Nadawcy" pokazuje
dzięki temu satelity podłączone, ale jeszcze niezatwierdzone), w jakim jest stanie (snapshot
do hydratacji dashboardu „Klienci"; dalsze zmiany idą SSE) i co zadeklarował w handshake
(żeby rejestracja z Web UI zapisała w World **prawdziwe** capabilities zamiast zgadywać typ
klienta). Wcześniej były to **trzy gołe kolekcje** tworzone w `main.py` i wędrujące przez
sygnatury dwóch fabryk routerów; przy rozłączeniu trzeba było pamiętać o sprzątnięciu
wszystkich trzech, w trzech osobnych linijkach — wzorzec, w którym pierwszy zapomniany wpis
zostaje w pamięci na zawsze i objawia się jako klient „podłączony", którego nie ma. Zero
wiedzy o rejestracji, pokoju czy tożsamości: to należy do `World` (sekcja 5).

**`is_production_ready` pyta o właściwość, nie o nazwę klasy (2026-08-30)** — `GET /voice/status`
liczy tę flagę z `is_placeholder` zadeklarowanego przez sam konkret (`ports/{stt,tts,wakeword}.py`).
Dawne `name.startswith("Mock")` i porównanie ze stringiem `"ThresholdEnergyWakeWordDetector"`
działały dopóty, dopóki nikt nie nazwał dev-providera inaczej — a fałszywe `true` oznaczałoby
pipeline, który nigdy nie rozpozna słowa „Regis".

### 3.6 Warstwa Wspólna (`packages/shared/src/shared`)
- **`ConfigStore` (`config.py`)**: Centralny zarządca persystentnej konfiguracji w formacie JSON z automatyczną walidacją i domyślnymi wartościami.
- **`EventBus` (`event_bus.py`)**: Asynchroniczna magistrala zdarzeń pub/sub (`subscribe`/`publish`). **W pełni wpięta w przepływ strumieniowania** — `AgentEngine` publikuje zdarzenia `ServerEventType.CHAT_CHUNK/DONE/ERROR/CANCELLED` oraz `TOOL_CALL_START/TOOL_CALL_RESULT` (kroki pętli ReAct), otagowane `session_id` **i** `target_client_id` (patrz sekcja 3.5, `ToolResult.redirect_sender_id`), a `interact_stream` subskrybuje je i tłumaczy z powrotem na strumień ustrukturyzowanych `StreamEvent` (`agent/engine.py`) dla wywołującego. **Treść `CHAT_ERROR` jest zawsze ogólna** (`TurnRunner._finish_failed`, `agent/turn.py`) — pełny techniczny szczegół wyjątku trafia wyłącznie do `logger.error` (konsola + `data/logs/regis.log`), nigdy do `EventBus`/pamięci sesji/UI. Powód: surowe błędy API dostawców LLM potrafią nieść wewnętrzne dane konta (zaobserwowane na żywo: ID organizacji Groq w treści błędu 429) — nie powinny wyciekać do żadnego z trzech odbiorców zdarzenia (SSE Chat UI, `interact()`, `voice/gateway.py`::`_on_error_or_cancelled` wysyłający `detail` do satelity), które wszystkie czerpią z tego samego payloadu, więc jedna sanityzacja u źródła zabezpiecza wszystkie na raz. Dzięki temu rdzeń nie zna bezpośrednio odbiorców — dziś dwóch: SSE (HTTP, `routes/chat.py`, subskrypcja per-request) i WS satelit głosowych (`server/voice/gateway.py`, subskrypcja ciągła per-połączenie, patrz sekcja 3.5). `routes/chat.py` serializuje `StreamEvent` na ramki SSE z polem `type` (`chunk`/`tool_start`/`tool_result`). Ustrukturyzowany ślad kroków (`ToolStepPayload`: `call_id`/`name`/`text_offset`/`arguments`/`content`/`is_error`) trafia też — gdy tura użyła narzędzi — do `metadata.steps` finalnej wiadomości `assistant` w `MemoryManager`, więc Web UI potrafi odtworzyć całe drzewko ReAct (tekst/COT przeplecione z wywołaniami narzędzi) zarówno na żywo, jak i po powrocie do historii sesji.
- **`contracts.py`**: Definicje obiektów transferu danych (DTO) współdzielonych przez serwer i konsolę WWW:
  - **System**: `HealthResponse`.
  - **Dostawcy LLM**: `LLMProviderDTO`, `LLMProviderListResponse`, `SelectLLMProviderRequest`, `CreateLLMProviderRequest` oraz generyczna specyfikacja opcji (`ProviderOptionSpec`, `ProviderTypeSpecDTO`, `ProviderMetadataResponse`) — schema-driven forma uzasadniona realną wymiennością backendu LLM (Ollama/OpenRouter).
  - **Czat i sesje**: `ChatMessageDTO`, `SendChatMessageRequest` (w tym opaque `sender_id`), `ChatResponseDTO`, `ChatSessionSummaryDTO`, `ChatSessionHistoryResponse`, `ChatSessionListResponse`, `CancelChatApiRequest`.
  - **Profile promptu Świata** (CRUD, do 3, `world/api/prompts.py`): `PromptDTO`, `PromptListResponse`, `CreatePromptRequest`, `UpdatePromptRequest`. **Fallback promptu kernela** (jedna wartość, `network/routes/prompts.py`): `AgentDefaultPromptDTO`.
  - **Telemetria wywołań LLM** (`network/routes/telemetry.py`): `GenerationLogEntryDTO` (wiersz listy — **bez** zrzutu wiadomości: przy 2000 rekordów po kilkanaście kilobajtów lista byłaby nie do wysłania, a inspektor i tak dociąga szczegół osobnym żądaniem), `GenerationLogDetailDTO`, `GenerationMessageDTO`, `GenerationAttemptDTO`, `GenerationLogListResponse`.
  - Prywatne słownictwo Home Assistant/satelit (config, katalog, grupy, rejestracje) żyje lokalnie w `world/dto.py`, nie tutaj — nie ma potrzeby generycznego kształtu skoro istnieje dokładnie jeden silnik.
- **`logging.py`**: Jednolita konfiguracja logów dla całego monorepo z ustandaryzowanymi nazwami kategorii (`regis.main`, `regis.agent`, `regis.world`, itp.). `setup_logging(level, log_file=None)` — konsola zawsze (kolorowany `MinimalColorFormatter`), opcjonalnie też plik z rotacją (`RotatingFileHandler`, 5 MB × 3 kopie, `PlainFileFormatter` bez kodów ANSI, pełna data). `main.py` przekazuje `data/logs/regis.log` (gitignorowane jak reszta `data/`) — dodane 2026-08-21, bo błędy tury (np. surowa treść odpowiedzi błędu API dostawcy LLM, potencjalnie z wewnętrznym ID organizacji) świadomie **nie** trafiają wprost do użytkownika (patrz niżej, `TurnRunner._finish_failed`) i bez pliku ginęłyby bezpowrotnie po przewinięciu terminala.
- **`correlation.py` (2026-08-25)**: `TurnRef` + `ContextVar` `current_turn` + `bind_turn()` — tożsamość tury przenoszona przez cały asynchroniczny przebieg bez przekazywania jej przez sygnatury. Mieszka w warstwie wspólnej, bo **ustawia ją kernel, a odczytuje obserwator** (`server/telemetry`): gdyby należała do obserwatora, `agent/` musiałby go zaimportować. Korelacja jest bytem tej samej natury co logowanie — infrastrukturą przekrojową, nie domeną. Działa, bo tura żyje w dokładnie jednym `asyncio.Task` (`AgentEngine._spawn_turn`), więc kontekst propaguje się w dół automatycznie. Patrz sekcja 3.8.
- **`version.py`**: `__version__` — **jedyne źródło prawdy o wersji produktu** w całym monorepo. Czytają je log startowy serwera, `GET /api/v1/health`, tytuł OpenAPI, plakietki w Web UI, tag obrazu Dockera i `deploy/deploy.sh`. Numery `version` w plikach `pyproject.toml` to wersje *pakietów*, których nikt nie publikuje — świadomie nieruszane przy wydaniu. Wcześniej ten sam numer był wpisany ręcznie w siedmiu miejscach i każde starzało się osobno.
- **`paths.py`**: `data_dir()`/`config_dir()` (`REGIS_DATA_DIR`/`REGIS_CONFIG_DIR`, fallback na korzeń usługi), `user_state_dir()` i `is_frozen()`. Powstało, bo `get_service_root()` szuka `pyproject.toml` **w górę od pliku źródłowego** — wzorzec działający wyłącznie przy uruchomieniu z checkoutu i przewracający się w obu postaciach produkcyjnych: w obrazie Dockera pakiet siedzi w `site-packages` (gdzie tego pliku nie ma, więc `data/` lądowałoby tam i znikało przy aktualizacji), a w bundlu PyInstallera źródła są w katalogu tymczasowym (więc satelita generowałaby nowy `sender_id` przy każdym starcie). Jedna warstwa naprawia oba przypadki; `get_service_root()` zostaje wyłącznie jako jej fallback.
- **`env.py`**: wczytanie `.env` (własny parser, ~25 linii — `python-dotenv` byłby zależnością wielokrotnie większą od potrzeby, precedens: `discovery.py`) oraz typowane gettery. **Zmienne obecne w środowisku wygrywają z plikiem**, żeby `docker compose`/`docker run -e` były przewidywalne. Nadpisania na `Settings` są celowo wąskie (`REGIS_HOST`/`REGIS_PORT`/`REGIS_DEBUG`) i **muszą pozostać rozłączne** ze zbiorem pól zapisywanych przez `PUT /api/v1/voice/client-config` — ten endpoint czyta ustawienia i zapisuje całość z powrotem do pliku, więc nadpisanie pola edytowalnego z Web UI zostałoby przy pierwszym zapisie zabetonowane w JSON-ie.
- **`secrets.py`**: referencje `env:NAZWA` w wartościach opcji dostawców i w tokenie Home Assistant. Nie migracja kluczy do `.env`, tylko **pośrednictwo** — bo dostawcy są wielo-instancyjni („Groq (kontakt@)", „Groq (zapasowy)" to dwa presety z osobnymi kluczami, zarządzane CRUD-em), więc jedna zmienna `GROQ_API_KEY` nie miałaby sensu; wiązanie musi zostać przy instancji. Prefiks jest jednoznaczny, więc rozwiązywanie nie potrzebuje wiedzy o tym, które pole jest sekretne, i mieści się w **dwóch punktach na granicy budowy konkretu**: `ProviderRegistry.build_provider()` (LLM/STT/TTS razem) i `WorldEngine._build_client()`. `load_all_instances()` celowo **nie** rozwiązuje niczego — zasila warstwę REST i CRUD, więc prawdziwy klucz nie ma prawa się tam pojawić. Maskowanie przepuszcza referencje: to nazwa zmiennej, nie sekret, i jest jedynym sygnałem, po którym poznaje się, że instancja bierze klucz ze środowiska.
- **`voice_frames.py` (2026-08-30)**: typowana postać kontraktu ramek — modele Pydantic + `encode_frame()`/`decode_server_frame()`/`decode_satellite_frame()`. Do tej pory `voice_protocol.py` deklarował **nazwy** ramek, ale nie potrafił ich zakodować ani zdekodować, więc obie usługi robiły to ręcznie i osobno (`json.dumps` po jednej stronie, `frame["silence_duration_ms"]` na surowym dicie po drugiej) — jedyny kontrakt między usługami nietypowany Pydantikiem. **Format na drucie się nie zmienia**, co pilnuje test złotego wzorca: satelitę aktualizuje się ręcznie, na innej maszynie, więc rozjazd wersji jest tu stanem normalnym. Nieznany typ ramki daje `None`, nie wyjątek — nowszy serwer może mówić więcej, niż starsza satelita zna. Podział na dwie rodziny jest asymetryczny celowo: serwer dekoduje wyłącznie ramki satelity i odwrotnie.
- **`voice_protocol.py`**: Kontrakt ramek WS satelity (`SatelliteMessageType`/`ServerMessageType`/`SAMPLE_RATE_HZ`/`SAMPLE_WIDTH_BYTES`/`CHANNELS`) — przeniesiony tu z `server/voice/protocol.py`, bo od `desktop_satellite` (sekcja 3.7) jest to kontrakt między dwiema niezależnymi usługami, nie szczegół jednej z nich (ten sam powód, dla którego DTO REST żyją w `contracts.py`, nie w `server/network/`).
- **`audio.py`**: `peak_amplitude()` — szczytowa amplituda porcji PCM16 mono. Konsolidacja trzech niezależnie powstałych, bajt-w-bajt identycznych kopii tej samej funkcji: lokalny VAD satelity (`desktop_satellite/vad.py::SilenceVadDetector`), serwerowy placeholder wake-worda (`server/ai/wakeword/detectors.py::ThresholdEnergyWakeWordDetector`) i serwerowa bramka przed STT (`voice/session.py::VoiceSession.handle_utterance_end`) — wszystkie trzy mierzą to samo pojęcie "głośności" ramki tym samym wzorem, więc czwarta kopia (przy dodawaniu bramki STT) przekroczyła próg uzasadniający DRY (Boy Scout Rule, `AGENTS.md`).
- **`discovery.py`**: Kontrakt UDP auto-discovery — `DISCOVERY_UDP_PORT`, `DISCOVERY_MAGIC` (odsiewa obcy ruch UDP na tym porcie) i czyste funkcje `encode_beacon`/`decode_beacon` (JSON `{"service", "port"}`). Współdzielony przez `server/discovery.py` (nadawca) i `desktop_satellite/discovery.py` (odbiorca) — bez uwierzytelniania, spójnie z modelem zaufanej sieci lokalnej przyjętym dla `WS /ws/voice/{sender_id}` (sekcja 5).

### 3.7 `desktop_satellite` — realny klient satelity desktopowej (`services/desktop_satellite/src/desktop_satellite`)

Pierwsza realna (nie-symulowana) implementacja satelity — długo działający proces
konsolowy na Windows/Linux, niezależna usługa `services/*` (nie importuje
niczego z `services/server`, łączy je wyłącznie `packages/shared` i protokół WS).

- **`protocol_client.py`**: `ProtocolClient` — cienki klient `websockets` kodujący/dekodujący ramki zgodnie z `shared/voice_protocol.py`, symetryczny do `VoiceConnection` (`server/voice/gateway.py`) z odwróconą rolą klient/serwer.
- **`session.py`**: `SatelliteSession` — klienckie odbicie automatu `VoiceSession`: `LISTENING_WAKEWORD` → (odbiór `wake_detected` od serwera — wake-word nadal wykrywa **serwer**, dziś placeholder `ThresholdEnergyWakeWordDetector`, satelita tylko ciągle strumieniuje mikrofon) → `RECORDING_UTTERANCE` (lokalny `vad.SilenceVadDetector` decyduje, kiedy wysłać `utterance_end` — zgodnie z decyzją "VAD po stronie satelity" niżej) → `PROCESSING` (mikrofon wstrzymany, ten sam powód co po stronie serwera: uniknięcie nagrywania własnego odtwarzania) → `SPEAKING` (odbiór `tts_start..tts_end`, odtworzenie, `playback_done`) → powrót do nasłuchu. Czysty automat + wstrzyknięte zależności (`link`/`speaker`/`vad`), testowalny bez gniazda/sprzętu (`tests/test_session.py`), tym samym wzorcem co serwerowy `VoiceSession`.
- **`vad.py`**: `SilenceVadDetector` — czysta klasa (mirror stylu `ThresholdEnergyWakeWordDetector`), wyzwala się po skonfigurowanym czasie ciągłej ciszy licząc od startu nagrywania (nie tylko po realnej mowie — **poprawione 2026-08-20**: wcześniejsza wersja czekała na choć jedną głośną ramkę, więc satelita wisiała bez końca w `RECORDING_UTTERANCE`, jeśli użytkownik nic nie powiedział po wake-wordzie; sam wymóg pełnego progu ciszy już chroni przed przedwczesnym wyzwoleniem). Testowalna w izolacji (`tests/test_vad.py`). Amplitudę ramki liczy przez `shared.peak_amplitude` (sekcja 3.6), nie własną kopią.
- **`audio.py`**: `MicCapture`/`SpeakerPlayback` przez `sounddevice`+`numpy` (PortAudio, Windows/Linux) — PCM16 mono 16 kHz, ramki 20 ms. `SpeakerPlayback.play_cue()` **(2026-08-20)** odtwarza wake/stop-tone preferencyjnie jako wbudowany dźwięk systemowy Windows Speech Recognition (`C:\Windows\Media\Speech On.wav`/`Speech Sleep.wav` — te same dźwięki, które kiedyś towarzyszyły Cortanie; własność użytkownika/Windows, nigdy nie kopiowane do repo, odtwarzane przez `winsound.PlaySound`), z fallbackiem do `synth_tone()` (lokalnie syntezowany sinusoidalny beep) na Linux albo gdy plik nie istnieje. Zero strumieniowania dźwięku z serwera w obu wariantach.
- **`main.py`**: CLI (`--server-url`/`--sender-id`/`--log-level`, wszystkie opcjonalne), pętla reconnect z backoffem (log + `asyncio.sleep`), czyste zamknięcie mikrofonu na `KeyboardInterrupt`.
- **`config.py`**: `SatelliteSettings` (`ConfigStore`+`get_service_root`, mirror `server/config.py`) — `sender_id: str` z `default_factory=uuid.uuid4`, trwale zapisywany w `services/desktop_satellite/config/settings.json` przy pierwszym uruchomieniu (brak pliku). Bez flagi `--sender-id` `main.py` używa `load_or_create_sender_id()` — ten sam UUID przy każdym kolejnym starcie, bez ręcznego wpisywania.
- **`discovery.py`**: `discover_server()` — nasłuchuje UDP broadcast serwera (`shared/discovery.py`), buduje `ws://{ip nadawcy}:{port z beaconu}/ws/voice`. Bez flagi `--server-url` `main.py` wywołuje to przed każdą próbą połączenia (bez cachowania ostatniego znanego adresu — KISS, broadcaster serwera działa non-stop, ponowne odkrycie kosztuje najwyżej jeden interwał rozgłoszenia).
- **Wake-word i STT/TTS: realne od tej sesji** (serwerowy `OnnxWakeWordDetector`, `GroqSTTProvider`/`ElevenLabsTTSProvider`, sekcja 3.5) — klient desktopowy dowodzi poprawności całego protokołu, lokalnego VAD i realnego pipeline'u głosowego (transkrypcja/synteza wymagają wklejenia własnych kluczy API w Web UI, zakładka Głos — bez kluczy łagodna degradacja do Mock*).

---

### 3.8 `server/telemetry` — obserwator wywołań LLM (zakładka „Logi", 2026-08-25)

Warstwa konkretna składana w `main.py`, dokładnie jak `server/ai`: implementuje
`BaseLLMProvider` z `ports/`, a kernel nigdy nie zna jej z nazwy. Powstała, bo
**dwie najważniejsze części promptu są z natury ulotne** i nie da się ich odtworzyć
z niczego po fakcie: `system_prompt` budowany przez `WorldEngine` co turę (i
zmienialny przez użytkownika w środku rozmowy) oraz `turn_context`, który
`ContextBuilder` wstawia tuż przed pytaniem i który **nigdy** nie trafia do
`data/sessions/*.json`.

- **Jednostką zapisu jest pojedyncze `generate_stream()`, nie tura i nie sesja.** W jednej turze pętla ReAct woła model do `max_tool_iterations` razy, a `working_messages` rośnie między wywołaniami o wynik każdego narzędzia — zapis per tura zlepiłby te warianty i zgubił dokładnie tę różnicę. Przynależność jest zdenormalizowana w rekordzie (`session_id`/`turn_id`/`call_index`), więc widok „po sesjach/turach" powstaje przez grupowanie w zapytaniu, a nie przez drugi model danych.
- **`RecordingLLMProvider` (`recorder.py`)** — dekorator opakowujący `LLMRouter`; widzi `messages`+`tools` na wejściu i strumień na wyjściu, mierzy TTFT/`total_ms`/`output_tps`, liczy `ToolCallRequest`, przechwytuje `GenerationUsage`. Musi proxy'ować `model`/`max_tokens`, bo `AgentEngine.interact()` czyta `llm_provider.model`. Zna też odpowiedź na pytanie, **czy tura w ogóle doszła do modelu** — stąd jego druga rola: subskrybuje `CHAT_DONE`/`CHAT_ERROR`/`CHAT_CANCELLED` i zapisuje wpis `no_generation` dla przebiegów, po których nie zostaje żadne żądanie (padnięty silnik świata przy budowie kontekstu, natychmiastowe anulowanie). Bez tego statusu najciekawsze awarie byłyby w panelu niewidoczne.
- **Korelacja przez `shared/correlation.py`** (`TurnRef` + `ContextVar` + `bind_turn()`) — `TurnRunner.run()` wiąże tożsamość tury na czas jej trwania, a ponieważ tura to jedno `asyncio.Task`, kontekst propaguje się w dół do dekoratora bez ani jednego dodatkowego parametru. Zmienna mieszka w `shared`, **nie** w `telemetry/`: ustawia ją kernel, czyta obserwator — gdyby należała do obserwatora, `agent/` musiałby go zaimportować i zależeć od czegoś, co ma go tylko obserwować.
- **`LLMAttempt` / `attempt_observer` (`ai/llm/router.py`)** — sekwencja prób łańcucha fallbacku (odrzucenie przed pierwszym fragmentem, pominięcie po circuit breakerze albo budżecie TPM) jest widoczna **wyłącznie wewnątrz routera**, czyli pod dekoratorem; dla warstw wyżej cała ta sekwencja wygląda jak jedno wywołanie. Dotąd ta wiedza kończyła się w `logger.warning`. Obserwator jest opcjonalny, synchroniczny i nieblokujący, a jego wyjątek kończy w logu — router działa tak samo bez niego. `TurnAttemptCollector` powstaje **przed** oboma stronami i jest wstrzykiwany do routera i do dekoratora, bo inaczej konstrukcja byłaby cykliczna.
- **Wejście i wyjście w JEDNYM rekordzie (2026-08-25, druga iteracja).** Rekord niesie nie tylko zrzut kontekstu, ale też to, co model na niego wygenerował: `answer`, `reasoning` i `response_tool_calls`. Powiązanie nie potrzebuje żadnego klucza obcego — wpis **jest** jednym `generate_stream()`, więc wyjście jest z definicji odpowiedzią na wejście z tego samego wpisu. Odtwarzanie odpowiedzi z kolejnego rekordu tury (kontekst wywołania #1 zawiera przecież `assistant`+`tool` z #0) odrzucone z dwóch twardych powodów: działa dla rund pośrednich, ale **nie dla ostatniej** — finalna odpowiedź idzie do pamięci sesji, nie do `working_messages`; a **rozumowanie nie wraca nigdy i donikąd**, bo `ReasoningChunk` z założenia nie trafia ani do pamięci, ani z powrotem do modelu, więc dekorator na porcie jest jedynym miejscem w systemie, które je w ogóle widzi. Konsekwencja dla estymaty: gdy dostawca nie poda `usage`, tokeny wyjściowe liczone są z `answer` **plus** `reasoning` — dostawca nalicza jedno i drugie.
- **`GenerationLogStore` (`store.py`) — jedyna baza SQLite w projekcie, świadomy precedens.** Cała konfiguracja Regisa siedzi w JSON-ach (`ConfigStore`, `JsonInstanceRepository`) i dla niej to właściwy wybór: kilka wpisów, cykl „wczytaj-zmień-zapisz", plik otwieralny edytorem. Telemetria ma **odwrotny profil**: tysiące rekordów, wyłącznie dopisywanie, odczyt zawsze z filtrem i sortowaniem po czasie, plus rotacja — `JsonInstanceRepository` oznaczałby `glob()` po tysiącach plików przy każdym otwarciu zakładki. To inny problem, więc inny magazyn; nie jest to zaproszenie do przenoszenia konfiguracji do bazy. Plik: `data/telemetry/generations.db` (gitignorowane jak reszta `data/`), WAL, jedna tabela `generations`, indeksy po `created_at` i `(session_id, turn_id, call_index)`.
- **Zapis nigdy nie opóźnia tury**: `submit()` wrzuca rekord do `asyncio.Queue` i wraca; jeden writer scala wsad w transakcję przez `asyncio.to_thread` (ten sam wzorzec co `TurnRunner._persist`). Pełna kolejka porzuca **najstarszy** wpis, a każdy wyjątek writera kończy w logu — przeciążenie obserwatora ma kosztować jego własne dane, nigdy generowanie odpowiedzi. Połączenie SQLite otwierane i **zamykane** per operacja (`with sqlite3.connect(...)` domyka wyłącznie transakcję, nie połączenie — żywe połączenie trzyma plik zablokowany na Windows). Rotacja jest leniwa, co kilkadziesiąt zapisów, bez timera i bez wątku w tle; limity: `Settings.telemetry_retention_records` (2000) i `telemetry_max_record_bytes` (256 KB, po przekroczeniu ucinane są **treści** wiadomości, struktura zostaje, wpis dostaje flagę `truncated`).
- **Telemetria zapisuje SUROWĄ treść błędów dostawcy**, w odróżnieniu od czatu, który pokazuje `USER_FACING_ERROR` (sekcja 3.6, `EventBus`). To świadomy rozdział, nie niespójność: ten sam błąd musi być zredagowany w UI (potrafi nieść wewnętrzne ID konta) i jest bezużyteczny zredagowany w narzędziu do debugowania. Panel jest lokalny i nie opuszcza maszyny.
- **Migracja schematu jest addytywna** (`_add_missing_columns`): `CREATE TABLE IF NOT EXISTS` nie dotyka istniejącej tabeli, więc każde rozszerzenie rekordu wymaga `ALTER TABLE ADD COLUMN` z wartością domyślną, wykonywanego przy starcie na podstawie `PRAGMA table_info`. Stare wpisy zostają i mają pusty nowy zakres. Wystarcza, dopóki kolumny wyłącznie przybywają — zmiana typu albo usunięcie kolumny wymagałaby prawdziwej migracji i to jest miejsce, w którym trzeba by ją napisać.
- **REST**: `network/routes/telemetry.py` — `GET /api/v1/telemetry/generations` (lista od najnowszej, kursor `before_id`, filtry `session_id`/`turn_id`/`status`), `GET .../{id}` (pełny zrzut wejścia **i** wygenerowanego wyjścia), `DELETE .../generations`. Wiersz listy celowo nie niesie ani kontekstu, ani odpowiedzi — inspektor dociąga jeden wpis osobnym żądaniem. Prefiks `telemetry`, **nie** `logs` — `data/logs/regis.log` to inny byt i endpoint nie może sugerować, że go serwuje.
- **Kierunek zależności**: `telemetry -> ai` (po `LLMAttempt`), `telemetry -> ports`, `telemetry -> shared`. Krawędź do `ai` jest jednokierunkowa i świadoma — obserwator sekwencji prób musi mówić jej słownictwem. Odwrotnie nie wolno:
  ```bash
  grep -rn "from server.telemetry" services/server/src/server/agent/ services/server/src/server/ai/
  ```
  (poprawny wynik: brak trafień)

---

### 3.9 Warstwa wdrożeniowa (2026-08-30)

Nie jest to warstwa kodu, tylko zestaw decyzji, bez których projekt zostaje prototypem
uruchamianym z konsoli. Wszystkie mieszkają poza usługami: `services/server/Dockerfile`,
`docker-compose.yml`, `deploy/`, `services/desktop_satellite/{build,install}.*`.

**Serwer: kontener na Raspberry Pi 5** (Pi OS Lite 64-bit, arm64). Obraz budowany
**natywnie na Pi**, bez QEMU i bez rejestru obrazów — aktualizacja to `deploy/deploy.sh`,
który przełącza tag, przebudowuje obraz i **czeka na `/api/v1/health`**, zamiast kończyć
się na `docker compose up -d`. Przeniesienie na mini-PC amd64 nie wymaga zmian w Dockerfile,
tylko rebuildu na tamtej maszynie. Python 3.13 jest tu bezpieczny: `onnxruntime` 1.29
(zależność `livekit-wakeword`) publikuje koło `cp313-manylinux_2_28_aarch64`, a bookworm
ma glibc 2.36.

**`network_mode: host` jest warunkiem koniecznym, nie preferencją.** `server/discovery.py`
rozgłasza obecność serwera przez UDP `<broadcast>`, dzięki czemu satelity znajdują go **bez
żadnej konfiguracji po swojej stronie** — a broadcast z sieci bridge nie wychodzi do LAN-u.
Konsekwencje: sekcja `ports:` byłaby ignorowana (port bierze się wyłącznie z `REGIS_PORT`
albo `config/settings.json`), a na Docker Desktop dla Windows/macOS sieć hosta nie działa
tak samo i każda satelita wymagałaby jawnego `--server-url`.

**Dane i konfiguracja to bind-mounty, nie wolumeny nazwane** (`./data`, `./config`) — pliki
mają zostać zwykłymi plikami na hoście: backup to `tar` katalogu, a `data/backends/*.json`
da się w razie czego otworzyć edytorem bez wchodzenia do kontenera. Model wake-word
(`data/wakeword/regis.onnx`) jest gitignorowany, więc **nie przyjeżdża z repozytorium** —
jego brak nie jest błędem, tylko cichą degradacją do placeholdera progu amplitudy, dlatego
`deploy.sh` o nim ostrzega.

**Satelita: aplikacja bez okna z ikoną w zasobniku.** Tryb bezokienkowy zabiera jedyny
dotychczasowy kanał onboardingu — README kazał odczytać `sender_id` z **logu startowego**,
żeby zarejestrować klienta w Web UI. Menu zasobnika przejmuje tę rolę i dlatego nie jest
ozdobą. `pystray` na Windows wymaga wątku głównego, więc punkt wejścia jest rozbity:
pętla `asyncio` mieszka w `app.py` (wątek roboczy, wystawia stan przez callback), a wątek
główny należy do ikony (`tray.py`). Autostart (`autostart.py`) to **przełącznik w menu**,
nigdy skutek uboczny instalacji: Windows przez `HKCU\...\Run` (`winreg` ze stdlib, bez
uprawnień administratora), Linux przez XDG `~/.config/autostart` — nie systemd, bo ten
startuje przed sesją graficzną, a satelita potrzebuje działającego PulseAudio/PipeWire.

Trzy pułapki buildu, każda cicha, każda rozbrojona:
- `--noconsole` oznacza brak `sys.stdout`; `StreamHandler(None)` wysypywał się przy
  pierwszym logu, czyli natychmiast po starcie, bez żadnego śladu (stąd warunek
  w `shared/logging.py` i plik logu **zawsze**, nie tylko w trybie bezokienkowym);
- build zrobiony przez `uv run` na współdzielonym `.venv` monorepo dał aplikację padającą
  na `DLL load failed while importing _ssl` — stąd samodzielny interpreter zarządzany przez
  `uv` i osobne `.venv-build` (build nie ma też prawa przestawiać wspólnego `.venv` na same
  zależności satelity i psuć środowiska serwera);
- PortAudio nie jest widoczne dla statycznej analizy PyInstallera — dołącza je hook contrib,
  a skrypty budujące **sprawdzają jego obecność w gotowym bundlu**, bo brak tej biblioteki
  nie wywala builda, tylko aplikację, i to dopiero przy pierwszym wake-wordzie.

Pełne runbooki: [`deploy/README.md`](../deploy/README.md) (serwer) i
[`services/desktop_satellite/README.md`](../services/desktop_satellite/README.md) (satelita).

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
- **`ServerEventType.CHAT_USER_MESSAGE`** (`events.py`) — nowe zdarzenie, publikowane w `TurnRunner.run()` zaraz po zapisaniu pytania użytkownika w pamięci. Dotąd treść promptu nigdy nie trafiała na `EventBus` (tylko do `MemoryManager`) — obserwator sesji zainicjowanej gdzie indziej nie miał jak dowiedzieć się, o co spytano, bez przeładowania historii.
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

- **Protokoły dostawców AI mieszkają w `server/ports/`, nie u konsumenta (rewizja 2026-08-24)**: Wcześniejszy zapis brzmiał „`BaseLLMProvider` zostaje w `agent/` — kernel jest jego właścicielem, tak jak `WorldInterface`". Ta własność **nie utrzymała się w praktyce**: dwa cykle importów między pakietami (`ai ↔ voice`, `agent ↔ ai`), łatane leniwymi importami w ciałach funkcji, były tego dowodem. Rewizja dotyczy wyłącznie portów, których konkrety mieszkają w `server.ai`; `WorldInterface` zostaje w `agent/`, bo `world -> agent` jest jednokierunkowe i żaden cykl tam nie powstał. Pełne uzasadnienie: sekcja „Warstwa portów" wyżej.

- **Wspólny magazyn instancji zamiast sześciu kopii (rewizja 2026-08-24)**: Manifest odraczał tę konsolidację do momentu, „aż wzorzec się ustabilizuje po dodaniu realnego drugiego typu STT/TTS". Warunek spełnił się **inaczej, niż zakładano**: drugi typ nadal nie istnieje, ale kopii wzorca „katalog plików JSON = kolekcja nazwanych instancji" było sześć (rejestry LLM/STT/TTS plus grupy, pokoje i profile promptu), i zaczęły się rozjeżdżać — `update_instance` miało w LLM sygnaturę `(id, name, options)`, a w STT/TTS `(id, options, name)`. To jest moment, w którym duplikacja przestaje być tania.

  Podział na trzy warstwy zamiast jednej klasy-kombajnu: `shared.JsonInstanceRepository` (pliki, lock, sanityzacja ID, pomijanie uszkodzonego wpisu), `ai.ProviderRegistry` (pojęcie instancji aktywnej + fabryka konkretu), podklasy domenowe (typy modeli, katalogi, zestaw startowy — 40-65 linii każda zamiast ~190). **Modele `*InstanceFileContent` zostają osobne** mimo identycznej struktury: ich scalenie zmieniłoby kolejność pól w serializacji, czyli bajty zapisywanych plików.

- **`check_health()` usunięte, nie naprawione (2026-08-24)**: Metoda była **abstrakcyjna** w `BaseLLMProvider`, więc każdy nowy dostawca musiał ją implementować — przy zerowej liczbie wywołań produkcyjnych. Dla dostawców OpenAI-compatible sprawdzała wyłącznie, czy klucz API jest niepusty, więc jako liveness check dawałaby zielone światło przy wygasłym kluczu i przy limicie (z tego samego powodu usunięto wcześniej zieloną diodę w czacie). Jeśli kiedyś pojawi się potrzeba realnego healthchecku — wróć do tej decyzji z konkretnym wymaganiem, nie z samą metodą.

- **Warstwa REST jest cienka z założenia (2026-08-24)**: Routery przyjmują żądanie, wołają domenę i tłumaczą wyjątek domenowy na kod odpowiedzi — nic więcej. Reguły w rodzaju „pominięte pole zachowuje obecną wartość" (upsert klienta) albo „pominięty sekret zachowuje obecną wartość" (klucze API) należą do domeny, bo obowiązują każdego wywołującego, nie tylko HTTP, i mają dawać się przetestować bez podnoszenia FastAPI. Stąd `ai/provider_crud.py` **nie zna HTTP** — rzuca wyjątki domenowe (`ProviderNotFoundError`, `UnsupportedProviderTypeError`), a `server.ai` nie zaczyna zależeć od warstwy transportowej.

  Routery zostały **jawne** (jedna deklaracja na endpoint), zamiast generowane z fabryki: adnotacje typów FastAPI czyta statycznie, więc fabryka wymagałaby podmieniania `__annotations__` w locie, a Swagger i tak musi widzieć osobne schematy per domena. Zysk jest tam, gdzie była masa — w ciałach handlerów.

- **Kontrola jakości jest zautomatyzowana, nie deklaratywna (2026-08-24)**: `AGENTS.md` wymagał ścisłego typowania, ale nic tego nie egzekwowało — i było to widać w kodzie (adnotacja `LLMRouter.generate_stream` nie wymieniała `ReasoningChunk` przez dwa dni po jego wprowadzeniu; `ProtocolClient._ws` wskazywał na klasę z przestarzałej gałęzi `websockets.legacy`, której `connect()` już nie zwraca). `ruff` + `mypy` są w trybie **raportującym, nie blokującym**: mają wskazywać dryf, a nie zatrzymywać pracę na dzień przepisywania adnotacji w działającym kodzie. Zestaw reguł ruff celowo wąski (`E4/E7/E9/F/I/B`) — błędy realne, higiena importów, oczywiste pułapki; zero reguł stylistycznych, bo projekt ma spójny, świadomy styl.


- **SQLite dla telemetrii, JSON dla konfiguracji (2026-08-25)**: `data/telemetry/generations.db` to **jedyna baza w projekcie** i świadomy precedens, nie początek migracji stanu do bazy. Kryterium jest profil dostępu, nie „nowocześniejszy magazyn": konfiguracja to kilka wpisów czytanych i przepisywanych w całości, telemetria to tysiące rekordów tylko dopisywanych, czytanych z filtrem i sortowaniem, z rotacją. `JsonInstanceRepository` obsłużyłby pierwsze i przewrócił się na drugim (`glob()` po tysiącach plików przy każdym otwarciu zakładki). **Nie przenoś tu konfiguracji** — jej profil się nie zmienił. Szczegóły: sekcja 3.8.

- **Telemetria zapisuje surowo, czat sanityzuje (2026-08-25)**: Ten sam błąd dostawcy trafia w dwa miejsca o przeciwnych wymaganiach — w UI musi być zredagowany (`USER_FACING_ERROR`, bo surowa treść potrafi nieść wewnętrzne ID konta, zaobserwowane na żywo przy 429 z Groq), a w narzędziu do debugowania zredagowany jest bezużyteczny. Rozdział jest zamierzony; panel telemetrii jest lokalny i nie opuszcza maszyny. Gdyby kiedykolwiek miał być wystawiony na zewnątrz, **to jest miejsce, do którego trzeba wrócić**.

- **Usunięcie generycznej wielorozszerzeniowości (`PluginProvider`/`Gateway`/`NetworkExtension`, warstwa `extensions/`)**: Wcześniejszy model "N niezależnych, wzajemnie nieświadomych rozszerzeń" bronił się przed scenariuszem (podmiana/wielość konkurencyjnych silników świata), który w tym prywatnym, jednoosobowym projekcie nigdy się nie wydarzył — jedynym realnym konsumentem od początku był Home Assistant, a rozszerzanie o satelity/kanał komunikacji tylko to potwierdziło. Próba utrzymania wzajemnej nieświadomości między dwoma bytami mającymi dokładnie jednego wspólnego konsumenta (satelita→pokój, filtrowanie encji HA) generowała realny koszt bez korzyści: albo Fakty nadużyte jako kanał międzyrozszerzeniowy (łamanie ich pierwotnej roli — wyłącznie dla agenta), albo rówieśniczy DI między dwoma osobnymi rozszerzeniami (dwie pary protokołów, cykliczne wiązanie w `main.py`). Scalono do jednego, konkretnego `WorldEngine` (`server/world/`), wołającego swoje wewnętrzne backendy wprost. Analogiczna decyzja do wcześniejszego usunięcia `DeviceIntegration` ABC — ten sam wzorzec zastosowany o jeden poziom wyżej. **Jeśli kiedyś pojawi się drugi, realny, jednocześnie używany silnik świata (nie tylko drugi backend smart home, ale odrębna domena możliwości agenta) — wróć do tej decyzji z konkretnym przypadkiem w ręku, nie z wyprzedzeniem.**
- **Modalność to capability klienta, nie parametr wywołania (rewizja 2026-08-22)**: Historia tej decyzji ma trzy etapy. (1) Pierwsza wersja trzymała kanał w `SatelliteRegistration.channel` — trwały config administrowany ręcznie, mogący rozjechać się z rzeczywistością. (2) Zrewidowane na `voice_mode: bool` — efemeryczny parametr wywołania dostarczany przez `server/voice` przez kernel do `WorldEngine.build()`, bo to gateway strukturalnie wie, czy interakcja jest głosowa. (3) **Zrewidowane ponownie**: `voice_mode` opisywał **wejście** ("przyszło głosem"), a sterował framingiem **wyjścia** ("odpowiadaj krótko, bo to będzie czytane"). To nie jest to samo pytanie — cel dostawy potrafi się zmienić w połowie tury (`speak_in_room`), a `system_prompt` powstaje raz, przed jej startem, i już tego nie nadgoni. Dodatkowo flaga zmuszała kernel do *przenoszenia* przez siebie wiedzy o kanale, choć nic z nią nie robił.

  Dziś `SenderProfile.capabilities: frozenset[ClientCapability]` (`mic`/`speaker`/`text`) jest **trwałym faktem o rzeczy w świecie**, dokładnie symetrycznie do istniejącego `Device.capabilities` — satelita z głośnikiem stojąca w Salonie jest takim samym bytem jak żarówka. Ryzyko rozjazdu z etapu (1) nie wraca, bo capabilities nie są wpisywane ręcznie: pochodzą z handshake WS (`hello.capabilities`, dotąd wyłącznie logowane) i są podawane przy rejestracji przez UI. `WorldInterface.build()` przyjmuje więc **wyłącznie `sender_id`** — kernel przestał cokolwiek wiedzieć o kanale, czyli stał się bardziej agnostyczny, nie mniej. Zmiana celu w trakcie tury nie potrzebowała nowego mechanizmu: `speak_in_room` zwraca nowe ramowanie w treści `ToolResult`, a wyniki narzędzi i tak wracają do modelu w pętli ReAct.

- **Formularz presetu LLM jest per MODEL, nie per dostawca (2026-08-23)**: Dotąd schemat opcji był wspólny dla całego typu dostawcy — `model`/`api_key`/`max_tokens` — a jedyny parametr generacji w systemie (`reasoning: {"effort": "none"}` dla OpenRoutera) był **zahardkodowany w fabryce**, czyli dokładnie ta rzecz, którą chce się stroić per model, była nietykalna. Jedna wspólna lista pól nie da się tu obronić: `reasoning_effort` istnieje dla gpt-oss i nie istnieje dla llamy, a dla Qwena **ma inny zestaw wartości** niż dla gpt-oss (zweryfikowane w dokumentacji Groq, nie zgadnięte). Dlatego `ProviderTypeSpecDTO.options_schema` niesie dziś wyłącznie pola niezależne od modelu (klucz API, adres serwera), a parametry generacji przychodzą razem z listą modeli (`ModelSpecDTO.options_schema`).

  **Trzy dostawcy, trzy źródła prawdy** — patrz sekcja 3.3, `model_catalog.py`. Wspólny mianownik: lista modeli nigdy nie zamyka wyboru, a niedostępność listy jest stanem konfiguracyjnym z opisem, nie błędem.

  **Nazwa presetu stała się własnym bytem.** Wcześniej UI wyprowadzało ją z pierwszej niesekretnej wartości formularza, przez co karta i badge w czacie pokazywały „openai/gpt-oss-120b (openai/gpt-oss-120b)" — nazwę modelu udającą nazwę presetu.

  **Kształt UI**: karta presetu **rozwija się w edytor w miejscu** (`components/provider_crud_section.js`). Modal odrzucono, bo projekt używa go wyłącznie do potwierdzeń i nie dałoby się porównać dwóch presetów; układ lista+formularz obok siebie odrzucono, bo to ten sam układ, który w sekcji Prompty zgłoszono do przebudowy jako ściśnięty. Koszt: aktywacja presetu przeniosła się z kliknięcia w kartę na osobny przycisk.

- **Zielona dioda przy modelu w czacie — usunięta (2026-08-23)**: Była zawsze zielona, niezależnie od czegokolwiek. `check_health()` istnieje na wszystkich providerach, ale **nie było nigdy wystawione w żadnym endpointcie**, a dla dostawców OpenAI-compatible sprawdza wyłącznie, czy klucz API jest niepusty — to nie jest liveness check, więc oparcie na nim diody dawałoby zielone światło przy wygasłym kluczu i przy limicie. Dekoracja udająca status poszła precz; jej miejsce zajął **quick-swap presetu**, który przełącza **globalnie aktywny** backend (`LLMRouter`), a nie „model tej rozmowy" — model per sesja wymagałby rozwiązywania dostawcy per turę w kernelu.

- **Łańcuch fallbacku LLM nie został uogólniony na STT/TTS (2026-08-25)**: `ProviderCrudSection` (front) jest już dziś generycznym, wspólnym komponentem dla LLM/STT/TTS — dodanie pola `Priority` tam kosztowało jedną flagę konfiguracji. Backend **nie jest** tak samo generyczny: `get_fallback_chain`/`set_fallback_chain` żyją wyłącznie w `BackendRegistry` (LLM), a `STTRouter`/`TTSRouter` to dziś proste resolvery jednego aktywnego providera, bez `CircuitBreaker`/chodzenia po kandydatach. Sprawdzone w logach przed decyzją (nie zgadywane): **zero** wystąpień 429/rate-limit dla Groq Whisper (STT) albo ElevenLabs (TTS) w całej historii projektu — wszystkie realne incydenty dotyczyły wyłącznie LLM. Limity STT/TTS mają też inny kształt (raczej sekundy audio/znaki niż tokeny/min), więc `TokenBudgetTracker` nie przeniósłby się 1:1. **Jeśli kiedyś pojawi się realny incydent STT/TTS — wróć do tej decyzji z konkretnym przypadkiem w ręku**: wzorzec (breaker + pole priorytetu w karcie) jest już zweryfikowany na LLM i przenosi się per domena w ograniczonym, znanym zakresie pracy, nie z wyprzedzeniem.

- **Przy trzech pozycjach właściwą kontrolką jest przełącznik, nie lista (2026-08-23)**: Sekcja Świat → Prompty miała układ „wąska lista po lewej, edytor po prawej", choć profili tożsamości może być najwyżej trzy (`MAX_PROFILES`). Z tej jednej pomyłki wynikały trzy niezależne objawy: kolumna listy miała stałą wysokość i setki pikseli pustki pod dwoma wpisami; edytor dostawał połowę szerokości, przez co pole Treść — **najdłuższy tekst w całej aplikacji** — pokazywało kilka linii i scrollowało się wewnątrz i tak scrollowanej strony; a akcje rozjeżdżały się na dwie kolumny. Dziś: pill-taby (ten sam komponent co nagłówek Ustawień) nad edytorem pełnej szerokości, a pole treści ma wysokość liczoną od okna.

  Techniczny szczegół warty zapamiętania: pole treści musi mieć `height`, nie `min-height` — rynna numerów linii rośnie z liczbą linii, więc przy `min-height` to ONA dyktowałaby rozmiar kontenera i pole rosłoby razem z promptem zamiast się przewijać (zmierzone: 1148 px przy realnym profilu).

  Identyfikator profilu zszedł z nagłówka do stopki: to metadana techniczna, nie tytuł, więc nie ma prawa konkurować wzrokowo z nazwą.

- **Lista urządzeń jest tabelą pogrupowaną po pokojach (2026-08-23)**: Przy realnej instalacji (siedem żarówek tego samego modelu) płaska lista kart renderowała **siedem wizualnie identycznych wierszy** — ten sam ucięty `entity_id`, ta sama nazwa, ten sam pokój, ten sam powtórzony ciąg możliwości — bez nagłówków mówiących, co jest czym. Trzy zmiany naprawiają to razem: nagłówki kolumn na siatce (wspólnej dla nagłówka i wierszy, więc kolumny naprawdę się pokrywają); **skracanie `entity_id` od ŚRODKA**, bo encje jednego urządzenia wielokrotnego różnią się wyłącznie sufiksem, czyli dokładnie tym, co ucinał dawny `text-overflow`; oraz grupowanie po pokoju — jedynym wymiarze, wzdłuż którego ta lista ma sens, i tym samym, którego używa `WorldEngine` renderując urządzenia do promptu.

  Możliwości stały się zwartymi znacznikami zamiast tekstu: dla urządzeń tej samej domeny są identyczne, więc jako powtórzony ciąg nie niosły żadnej informacji różnicującej. Doszło też przypisanie pokoju **hurtem** dla zaznaczonych wierszy — przy siedmiu identycznych żarówkach ustawianie go wiersz po wierszu to siedem razy ta sama czynność.

- **Zero natywnych kontrolek przeglądarki (domknięte 2026-08-23)**: Projekt konsekwentnie zastępuje domyślne kontrolki własnymi (`<select>` → `components/select.js`, `type="number"` → pole tekstowe, scrollbary → własny styl w `reset.css`). Ostatnie dwa natywne checkboxy — negacja w Kontekście tury i multi-select urządzeń w formularzu grupy — zniknęły: pierwszy razem z modelem negacji (dwie gałęzie tekstu), drugi zastąpiony własnym przełącznikiem trzymającym stan na `aria-checked`, czyli tam, gdzie i tak musi być dla czytników ekranu, zamiast w równoległym stanie JS. `grep -rn 'type="checkbox"' services/server/src/server/web/js/` nie ma dziś trafień.

- **TTS strumieniowany, nie sklejany w jeden bufor (2026-08-24)**: `BaseTTSProvider.synthesize_stream()` jest dziś prymitywem (mirror `BaseLLMProvider.generate_stream`) — yielduje kolejne fragmenty PCM16 w miarę powstawania; `synthesize()` zostaje jako konkretna metoda zbierająca strumień w jeden bufor (mirror `generate()`), dla wywołujących, którym strumieniowanie jest obojętne. Wcześniej `ElevenLabsTTSProvider.synthesize()` dostawał od SDK `AsyncIterator[bytes]` (`convert()`) i **sam** je sklejał (`b"".join(...)`), mimo że dostawca, protokół WS (`tts_start` -> N ramek binarnych -> `tts_end`) i odtwarzacz satelity od dawna umiały pracować strumieniowo — po prostu nic pomiędzy nimi z tego nie korzystało. Przy dłuższej odpowiedzi to była różnica między dźwiękiem od razu po zakończeniu tury a ciszą przez kilka sekund.

  `VoiceSession.speak()` wysyła `tts_start` i pierwszą ramkę, gdy tylko dostawca zwróci PIERWSZY fragment — `SYNTHESIZING` trwa dziś tyle, ile czas do pierwszego bajtu strumienia, nie do końca całej syntezy. Wyjątek dostawcy jest traktowany różnie zależnie od tego, czy coś już poszło do satelity: **przed** pierwszym fragmentem — klasyczna ścieżka błędu (`send_error` + powrót do nasłuchu, sanityzacja jak wszędzie: szczegół dostawcy tylko do logu). **Po** pierwszym fragmencie — `tts_end` wysyłane jak przy normalnym zakończeniu, bo satelita ma już czym karmić głośnik; ucinanie w pół zdania jest gorsze od próby dokończenia, ale wciąż lepsze niż zostawić satelitę czekającą na ramki, których nie będzie. Normalny mechanizm (`handle_playback_done()`) i tak wraca do nasłuchu, gdy satelita doigra to, co dostała.

  **`desktop_satellite`**: `SpeakerPlayback` dostał ścieżkę strumieniową (`start_stream`/`write_chunk`/`stop_stream`, `sd.RawOutputStream`) obok istniejącej `play()` (zostaje dla lokalnych dźwięków wake/stop-tone, gdzie cały bufor i tak powstaje lokalnie w jednej chwili). `stop_stream()` woła `Stream.stop()`, **nie** `abort()` — `stop()` czeka, aż wszystkie już przyjęte ramki dograją się do końca, więc `playback_done` wysyłane zaraz po nim naprawdę oznacza koniec odtwarzania, nie tylko koniec odbierania danych; `abort()` ucinałby ostatni fragment w połowie dźwięku. `start_stream()` defensywnie zamyka (`abort()`, świadomie nie `stop()` — strumień jest osierocony, nikt nie czeka na jego dogranie) każdy poprzedni strumień, który nie doczekał się `stop_stream()` (np. WS padł w połowie odtwarzania) — inaczej uchwyt PortAudio przeciekłby, nadpisany bez zamknięcia.

  `MockTTSProvider` strumieniuje ciszę w kawałkach ~200ms (nie jeden blok) — testy i ręczne demo bez klucza API widzą realnie wiele fragmentów, nie jeden udający strumień.

  Zweryfikowane na żywo przez pełny stos produkcyjny (bramka rejestracji, REST, `AgentEngine`, `VoiceConnection`, `VoiceSession.speak()`) na realnym koncie ElevenLabs: dwie kolejne przyczyny błędu (401 brak uprawnienia klucza, potem 402 głos biblioteki wymaga płatnego planu) obie poprawnie zakończyły się sanitized `error` do satelity i powrotem do `LISTENING_WAKEWORD` — potwierdzone przez `GET /voice/clients/status`. Sam udany przebieg wielu ramek binarnych nie został zweryfikowany na żywo (konto użytkownika nie miało w tej sesji odblokowanego głosu), pokrywają go za to dedykowane testy jednostkowe ćwiczące dokładnie tę samą, produkcyjną ścieżkę kodu z podstawionym dostawcą wielofragmentowym.

- **Katalog encji Home Assistant dociągany leniwie (2026-08-23)**: Wejście w zakładkę Świat pobierało sześć zasobów naraz, w tym `GET /world/catalog` — jedyny z nich, który kosztuje **żywe zapytanie HTTP do fizycznego Home Assistant** (zero cache po stronie `WorldEngine`). Potrzebuje go wyłącznie wyszukiwarka urządzeń, więc dziś leci przy pierwszym kontakcie z polem szukania, nie przy wejściu w zakładkę. Drugą połową problemu był placeholder „Ładowanie konfiguracji Świata…" — jedna niska karta, którą zastępowała pełna, wysoka treść, przez co kontenery skakały w pionie. Zastąpił go **szkielet o docelowej geometrii** (`css/components/skeleton.css`), a trzy panele zakładki montują się równolegle zamiast po kolei. Zweryfikowane pomiarem: wysokość strony w trakcie ładowania i po nim jest identyczna (7918 px), czyli zerowe przesunięcie układu.

  Przy okazji wyszukiwarka przestała przy pustej frazie wypisywać **cały** katalog (u użytkownika 97 encji nad zadeklarowaną listą) — pokazuje podpowiedź, a wyniki dopiero od pierwszego wpisanego znaku.

- **Reasoning rozdzielony strukturalnie, nie znacznikiem w treści (2026-08-23)**: Dostawcy LLM dostają rozumowanie modelu osobnym polem (`delta.reasoning`/`reasoning_content`/`thinking`), ale pierwsza implementacja wlewała je z powrotem do tego samego strumienia stringów co odpowiedź, owijając w `<think>…</think>`. Rodzaj tokena jest faktem strukturalnym, a ten model gubił go natychmiast po opuszczeniu providera — i jeden korzeń dawał **trzy** osobne objawy w trzech różnych warstwach: (1) `voice/gateway.py` sklejało cały strumień do bufora mowy, więc satelita czytała chain of thought na głos, a im dłuższy tekst, tym dłuższa synteza (to była zgłoszona "zwiecha w trybie Odpowiada"); (2) `MemoryManager` utrwalał rozumowanie w `content`, skąd wracało do modelu jako historia w **każdej** kolejnej turze; (3) Web UI odzyskiwało podział parsując strumień znak po znaku, buforując fragmenty na wypadek urwanego w połowie `<think>`.

  Dziś: `ReasoningChunk` (`ports/llm.py`) to trzeci typ yieldowany przez `generate_stream`, `CHAT_CHUNK` niesie `kind: "answer" | "reasoning"`, a odbiorca decyduje sam — Web UI pokazuje, TTS pomija, pamięć odkłada do `metadata.reasoning`. Bare `str` zostawiono jako "tekst odpowiedzi" celowo: wszystkie istniejące ścieżki `isinstance(event, str)` działają bez zmian i zaczynają filtrować rozumowanie za darmo.

  **Kolejność w `metadata` niesie `seq`, nie sam `text_offset`**: cała sekwencja myślenie → narzędzie → myślenie dzieje się przy offsecie 0, dopóki model nie napisze pierwszego znaku odpowiedzi, więc offset by ich nie rozróżnił.

  **Wiadomości sprzed tej zmiany NIE są migrowane** — pliki w `data/sessions/` to realne dane użytkownika, a nie schemat do przepisania. `step_rail.js::splitThinkFromText` zostaje jako ścieżka odczytu wiadomości bez `metadata.reasoning`; dla nowych wiadomości jest martwa.

- **Prompt tury dzielony wzdłuż ZMIENNOŚCI, nie tematu (2026-08-22)**: `ContextBuild` zwraca `system_prompt` (stabilne: tożsamość) i `turn_context` (zmienne: czas, urządzenia, ramowanie dostawy). Wcześniej był to jeden sklejony string trafiający w całości na pozycję zerową. Dwa realne skutki tamtego stanu: (1) tożsamości nie dało się edytować bez dotykania faktów, bo mieszkały w jednym polu; (2) znacznik czasu zmieniał wiadomość zerową przy KAŻDEJ turze, więc prefiks żądania nigdy się nie powtarzał i cache dostawcy nie miał się o co zaczepić. Przy sesjach rzędu 10-15 tur zysk kosztowy jest drugorzędny — głównym uzasadnieniem jest rozdzielenie własności treści. Efekt uboczny wykorzystany celowo: fakty lądują blisko pytania, gdzie modele trzymają się ich pewniej.

  **Tożsamość NIE jest zapisywana w historii** (`MemoryManager`), tylko budowana co turę ze stabilnej treści. Zapisanie jej jako wiadomości zerowej w pliku sesji rozważono i odrzucono: zamroziłoby profil w istniejących sesjach (dziś przełączenie działa natychmiast), a przycinanie historii do `max_history_messages` mogłoby ją z czasem wypchnąć z kontekstu.

  Rola wiadomości z faktami to `system` **w środku rozmowy** — zweryfikowane empirycznie na `openai/gpt-oss-120b` przed implementacją (model wprost cytuje ten blok w swoim rozumowaniu: "According to system…"), nie założone. Gdyby przyszły model ją ignorował, alternatywą jest rola `user` z jawnym markerem.

- **Sekcje kontekstu tury — komponowalna lista, nie stały zestaw slotów (2026-08-22)**: `world/prompt_sections.py` trzyma **uporządkowaną listę** sekcji (`data/world/prompt_sections.json`); kolejność listy = kolejność w prompcie. Każda sekcja ma warunek pojawienia się i **dwa teksty** — jeden na wynik pozytywny, drugi na negatywny. Użytkownik dodaje, usuwa i przestawia sekcje (drag-and-drop) w Web UI (Świat → Kontekst tury).

  **Ewolucja w dwóch krokach tego samego dnia.** Pierwsza wersja wyniosła literały do konfiguracji, ale jako sześć z góry zdefiniowanych slotów — czyli dokładnie tego, co silnik akurat liczy. Okazało się to za słabe: "gdy nadawca jest w Salonie, dodaj instrukcję X" było w tym modelu **niewykonalne bez zmiany kodu**. Lista z warunkami usuwa ten sufit.

  **To nadal nie jest język szablonów.** Warunki pochodzą z zamkniętej listy zdefiniowanej w `CONDITION_SPECS` i są ewaluowane w Pythonie — użytkownik ich **wybiera, a nie pisze**. Nie da się zrobić literówki w składni, nie ma sandboxa ani tracebacków z cudzego kodu. Odrzucono zarówno Jinja2 w textarea (literówka wywalałaby każdą turę), jak i jeden wielki szablon z placeholderami — ten drugi dałby kolejność, ale **traci warunkowość**: bez przypisanego pokoju `{pokój}` byłoby puste i zostałoby kalekie "Nadawca znajduje się w lokalizacji: .". Osobne sekcje pozwalają silnikowi pominąć CAŁY blok, bo tylko on wie, czy dane istnieją.

  **Dwie gałęzie tekstu zamiast dwóch sekcji (rewizja 2026-08-23)**: pierwsza wersja dawała sekcji flagę `negated`, więc „gdy NIE spełniony" wymagało **osobnego wpisu listy**. Jedna decyzja („czy klient ma głośnik?") była przez to rozbita na dwa wpisy, których nic formalnie nie łączyło — dało się je niezależnie przestawić w odległe miejsca promptu, a UI potrzebowało checkboxa „NIE" (jednej z ostatnich natywnych kontrolek przeglądarki w tym projekcie). Dziś sekcja ma `text` i `text_negated`; silnik wybiera gałąź po wyniku warunku, pusta gałąź znaczy „przy tym wyniku nie mów nic". **Świadomy koszt: obie gałęzie dzielą jedną pozycję w kolejności** — zaakceptowane, bo w praktyce zawsze stały obok siebie.

  Migracja **scala pary** (ten sam warunek i parametr, jedna zanegowana) w jedną sekcję, biorąc etykietę i pozycję od wpisu niezanegowanego; zanegowana sekcja bez pary zostaje osobnym wpisem z wypełnioną wyłącznie drugą gałęzią. Pliki w `data/` to realne dane użytkownika — migracja nie może po cichu zgubić tekstu, który ktoś wpisał.

  **Przestawianie przez drag-and-drop** (HTML5 DnD, zero zależności): strzałki góra/dół przerenderowywały całą listę na każde kliknięcie, więc przesunięcie o kilka pozycji było serią skoków z gubionym fokusem. Uchwyt jest osobnym elementem, nie całą kartą (inaczej nie dałoby się zaznaczyć tekstu), i przyjmuje fokus — strzałki z klawiatury zostają jako równoważna ścieżka, bo samo DnD jest niedostępne.

  **Warunki są czystymi funkcjami** `TurnFacts -> bool`. `WorldEngine.build()` składa `TurnFacts` raz na turę (czas, capabilities, pokój, wyrenderowana lista urządzeń, czy HA skonfigurowany), dzięki czemu każdy warunek testuje się bez żadnego I/O.

  **Ostrzeżenia informują, nie blokują**: użycie `{pokój}` w sekcji, której warunek go nie gwarantuje, zwraca `warnings` (także na GET, nie tylko po zapisie) — bywa zamierzone, więc odmowa zapisu byłaby nadgorliwa. Ważniejszy od walidacji jest **podgląd** (`GET /prompt-sections/preview?sender_id=`), składany przez **`WorldEngine.build()`**, czyli tę samą ścieżkę co realna tura; osobna, "szybsza" ścieżka renderowania prędzej czy później rozjechałaby się z produkcyjną i podgląd przestałby cokolwiek dowodzić.

  `speak_in_room` nie hardkoduje już zdania o przełączeniu na głos: przelicza sekcje dla NOWEGO celu i dokłada do wyniku narzędzia tylko te, które wcześniej nie obowiązywały (`_sections_gained_after_redirect`) — tekst pochodzi z tej samej konfiguracji, a model nie dostaje po raz drugi rzeczy, które już wie.

  **Granica edytowalności**: użytkownik edytuje to, co agent ma *usłyszeć*; silnik renderuje *dane*. Format wiersza urządzenia i nagłówki pokoi zostają w kodzie — zepsuty szablon wiersza po cichu zamieniłby całą listę urządzeń w śmieci. Podstawianie przez jawny `str.replace`, **nigdy `str.format`** (ten wysypuje się `KeyError` na każdym nawiasie klamrowym, a ludzie wklejają do promptów przykłady JSON).

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

- **Klucze API zostają przy instancji dostawcy, środowisko podaje wartość (2026-08-30)**:
  odrzucona została migracja kluczy do `.env` w rozumieniu „jedna zmienna na dostawcę".
  Powód: dostawcy są wielo-instancyjni i zarządzani CRUD-em z Web UI, więc `GROQ_API_KEY`
  nie ma jak wskazać, o który z trzech presetów Groq chodzi. Zamiast tego wartość opcji może
  być **referencją** `env:NAZWA` (`shared/secrets.py`) — wstecznie zgodne, bez momentu
  przełączenia i bez migracji istniejących danych. Warto pamiętać, czego to **nie** naprawia:
  klucze nigdy nie wyciekały do repozytorium (`.gitignore` blokuje `data/`), więc rozwiązywany
  problem to wstrzyknięcie klucza do kontenera, nie wyciek.

- **Wygaszanie sesji jest leniwe i mieszka w kernelu (2026-08-30)**: reguła „historia
  bezczynna dłużej niż N sekund zaczyna od zera" należy do `MemoryManager`, nie do bramki WS,
  bo obowiązuje każdego wywołującego kernela. Sprawdzenie jest czystą funkcją `updated_at`,
  więc **nie ma timera ani wątku w tle** — sesja, po którą nikt nie sięga, nikomu nie szkodzi.
  Politykę wnosi brzeg kompozycji (satelity dostają wartość z `Settings`, czat Web UI nie
  dostaje żadnej), więc kernel nadal nie wie, z jakim typem klienta rozmawia. Patrz sekcja 3.2.

- **Wersja produktu ma jedno źródło i nie jest polem konfiguracji (2026-08-30)**:
  `shared/version.py`. Usunięto ją z `Settings`/`settings.json` — numer wersji nie jest rzeczą,
  którą użytkownik edytuje w pliku konfiguracyjnym, a siedem ręcznie utrzymywanych kopii
  starzało się każda osobno. Wersje w `pyproject.toml` zostają jako wersje pakietów; nikt ich
  nie publikuje i nie rusza się ich przy wydaniu.

### Zaplanowane, jeszcze niezaimplementowane

1. **Pamięć Długoterminowa i Wektorowa**: Planowana integracja modułów pamięci wektorowej i semantycznej w usłudze `server`.
2. **Fizyczni klienci satelit (ESP32/desktop)**: Klient desktopowy (Windows/Linux, `services/desktop_satellite/`, sekcja 3.7) **istnieje od dwóch sesji wstecz** — pełny cykl audio (mikrofon+głośnik) przez `sounddevice`, lokalny VAD końca wypowiedzi, lokalnie syntezowane tony wake/stop (z fallbackiem do dźwięków systemowych Windows), auto-discovery serwera. Wake-word (`OnnxWakeWordDetector`) i STT/TTS (`GroqSTTProvider`/`ElevenLabsTTSProvider`, sekcja 3.5) są dziś realne — wymagają tylko wklejenia własnych kluczy API w Web UI (zakładka Klienci, dawniej Głos). Bez klucza TTS działa łagodna degradacja do `MockTTSProvider` (cisza); bez klucza STT `STTFactory` rzuca `STTNotConfiguredError` zamiast fabrykować fałszywą transkrypcję (patrz sekcja 3.5, rewizja 2026-08-21). Firmware ESP32 (I2S mikrofon/głośnik, lokalne tony wake/stop) nadal nie istnieje. Web UI pozostaje jedynym zawsze dostępnym nadawcą tekstowym: generuje i trwale zapisuje własny opaque `sender_id` w `localStorage` (`web/js/sender_id.js`) i wysyła go z każdym `POST /api/v1/chat*`, a zakładka "Świat" pozwala zarejestrować tę przeglądarkę (albo dowolny inny `sender_id`, w tym satelitę desktopową) pod pokojem.
3. **Widoczność kroków ReAct SPRZED dołączenia do sesji już w toku**: Od rewizji "wyślij i zapomnij + `watch_session()`" (sekcja 4.1) kroki narzędzi, które wystąpią PO otwarciu kanału obserwującego, renderują się już na żywo. Nadal niewidoczne: kroki, które wystąpiły ZANIM ktoś zaczął obserwować (np. przed przeładowaniem strony w trakcie długiej pętli ReAct) — `metadata.steps` z tamtego okresu istnieje dopiero po zakończeniu całej tury, w historii.
4. **Uporządkowanie warstwy Web UI**: Backend przeszedł refaktoryzację 2026-08-24, Web UI jeszcze nie. Znane, udokumentowane zaległości: 65 kopii bloku `try/fetch/!ok/catch` w czterech klientach domenowych (`web/js/network/clients/`), trzy kopie pętli czytnika SSE, `api_client.js` jako 60 metod czystej delegacji, nazwy plików nieodpowiadające zakładkom (`views/extensions*` to zakładka **Świat**, `voice_config.js` to **Klienci** — nazwy pochodzą z porzuconej wielorozszerzeniowości i ze starej nazwy zakładki), trzy różne konwencje cyklu życia widoku oraz dwa pliki po ~750 linii (`chat.js`, `chat/step_rail.js`) mieszające renderowanie DOM, transport SSE i czystą logikę segmentów. Zakres i kolejność: `REFACTORING_PLAN.md`, etap E9 (świadomie odłożony na osobną sesję
2026-08-30, razem z punktem 4 etapu E8 — reorganizacją `voice/routes.py` do `voice/api/*`;
pozostałe punkty E8, czyli typowany kodek ramek i rejestr obecności, są już wdrożone).
