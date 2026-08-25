# Onboarding i Przewodnik Deweloperski – System Regis

Dokument stanowi jednolity przewodnik po architekturze, konfiguracji środowiska, standardach kodowania oraz cyklu pracy w **Systemie Regis**. Jest to bezpośrednie źródło wiedzy przeznaczone zarówno dla dewelopera, jak i asystujących mu agentów sztucznej inteligencji.

---

## 1. Wymagania Wstępne i Środowisko

Projekt oparty jest o język Python w architekturze **monorepo** z menedżerem pakietów `uv`.

### Wymagania:
- **Python**: `>= 3.11`
- **Menedżer zależności**: `uv` (`pip install uv` lub poprzez oficjalny instalator Astral)

### Inicjalizacja repozytorium:
Wykonaj synchronizację pakietów i utwórz wirtualne środowisko w oparciu o plik `pyproject.toml`:
```bash
python -m uv sync
```

---

## 2. Konfiguracja

System Regis obsługuje zarówno dostawców lokalnych, jak i chmurowych. **Uwaga: żaden parametr konfiguracyjny nie jest obecnie odczytywany ze zmiennych środowiskowych** — cała konfiguracja jest persystentna i zarządzana wyłącznie przez moduł `ConfigStore` (`packages/shared/src/shared/config.py`), w postaci plików JSON na dysku.

### Parametry serwera (`services/server/config/settings.json`, model `Settings` w `server/config.py`):
- **`host`**: Adres nasłuchiwania interfejsu sieciowego (domyślnie: `0.0.0.0`).
- **`port`**: Port serwera HTTP/WebSocket (domyślnie: `8000`).
- **`llm_timeout`**: Globalny limit czasu zapytań do LLM w sekundach (domyślnie: `30.0`).
- **`llm_default_max_tokens`**: Domyślna maksymalna liczba tokenów wyjściowych (domyślnie: `4096`).
- **`max_history_messages`**: Maksymalna liczba ostatnich wiadomości z historii sesji dołączana do kontekstu LLM (domyślnie: `40`).
- **`max_tool_iterations`**: Maksymalna liczba rund wywołań narzędzi w jednej pętli agentycznej (domyślnie: `8`).
- **`telemetry_retention_records`**: Ile najnowszych zrzutów wywołań LLM trzyma zakładka **Logi** (domyślnie: `2000`, plik `data/telemetry/generations.db`). Rotacja jest leniwa — uruchamia się co kilkadziesiąt zapisów, nie z timera, więc chwilowo w bazie może być nieco więcej wpisów niż limit.
- **`telemetry_max_record_bytes`**: Sufit rozmiaru zrzutu kontekstu w jednym wpisie telemetrii (domyślnie: `262144`, czyli 256 KB). Po przekroczeniu ucinane są **treści** wiadomości — struktura (ile wiadomości, w jakich rolach) zostaje nietknięta, a wpis dostaje flagę `truncated` widoczną w UI jako badge „ucięto”.
- **`wakeword_model_path`**: Ścieżka (względna wobec katalogu usługi) do wytrenowanego modelu wake-word `.onnx` (domyślnie: puste — placeholder progu amplitudy `ThresholdEnergyWakeWordDetector`, łagodna degradacja gdy plik nieskonfigurowany/nie istnieje). Model kopiuje się ręcznie, np. do `data/wakeword/<nazwa>.onnx` (katalog `data/` jest w `.gitignore`).
- **`wakeword_threshold`**: Próg pewności detekcji wake-word, 0-1 (domyślnie: `0.65` — dla konkretnego modelu użyj wartości `optimal_threshold` z jego metryk ewaluacyjnych). Konfigurowalne przez Web UI (zakładka **Klienci**, `GET/PUT /api/v1/voice/client-config`), działa od razu bez restartu.
- **`vad_silence_duration_ms`** / **`vad_amplitude_threshold`**: Parametry VAD satelity (koniec wypowiedzi) — domyślnie `1500.0`/`500`. Algorytm wykonuje się lokalnie na satelicie (zero rundtripu na decyzję), ale próg jest centralnie skonfigurowany tutaj i wysyłany satelicie raz, zaraz po handshake (`ServerMessageType.CLIENT_CONFIG`, `shared/voice_protocol.py`) — zmiana działa po następnym reconnect satelity, bez restartu serwera. Konfigurowalne przez to samo `GET/PUT /api/v1/voice/client-config`.

### Parametry dostawców LLM (`services/server/data/backends/*.json`, zarządzane przez `BackendRegistry`):
- **`options.api_key`**: Klucz API wymagany do komunikacji z dostawcą OpenRouter (pole w instancji backendu, nie zmienna środowiskowa).
- **`options.base_url`**: Adres serwera Ollama (domyślnie: `http://localhost:11434`).
- **`options.tpm_limit`**: Opcjonalny limit tokenów/min presetu (np. `8000` dla darmowego tieru Groq) — włącza proaktywne pomijanie przez `TokenBudgetTracker` w łańcuchu fallbacku (patrz niżej); brak pola = tracker nie sprawdza budżetu dla tego presetu.

**Łańcuch fallbacku LLM** (`data/fallback_chain.json`, `BackendRegistry.get_fallback_chain()`/`set_fallback_chain()`): aktywny preset jest zawsze próbowany jako pierwszy (Priorytet 0); pozostałe presety dostają numer priorytetu w polu **Priority** na karcie w zakładce **Dostawcy** — puste pole wyklucza preset z automatycznego routingu. `LLMRouter` przełącza się na kolejnego kandydata WYŁĄCZNIE, gdy poprzedni padnie z błędem przed pierwszym fragmentem odpowiedzi (np. HTTP 429), z `CircuitBreaker` pomijającym niedawno padniętego kandydata w kolejnych turach. Pełne uzasadnienie i historia: `docs/manifest.md` sekcja 3.3 oraz sekcja 5 ("Łańcuch fallbacku LLM nie został uogólniony na STT/TTS").

### Parametry `WorldEngine` (`services/server/data/world/config.json`, zarządzane przez `WorldEngine`):
- **`base_url`** / **`access_token`**: Adres serwera Home Assistant i długoterminowy token dostępu (Long-Lived Access Token) — pola jawne, nie schema-driven (Home Assistant jest jedynym, znanym z góry backendem silnika). Home Assistant jest traktowany jako **jeden, globalny zasób (singleton)** — jeden `base_url`/`access_token`, bez wielości nazwanych połączeń. Puste pola oznaczają brak konfiguracji — `WorldEngine` degraduje się łagodnie (encje/narzędzia HA po prostu nie są dostarczane w danej turze), bez osobnego przełącznika `enabled`.

Grupy urządzeń przechowywane są w `services/server/data/world/groups/*.json`. **Pokoje** (`Room` — pełnoprawny byt World, niezależny od Home Assistant Areas, patrz `docs/manifest.md` sekcja 5) — w `rooms/*.json`, ten sam wzorzec pliku-na-instancję co grupy. Zadeklarowana lista urządzeń widocznych dla agenta (**opt-in** — `display_name`/`room_id` per `entity_id`) — w `declared_devices.json`; brak wpisu oznacza niewidoczność, niezależnie od tego, czy encja istnieje po stronie HA. Zarejestrowani klienci (`sender_id -> {display_name, room_id, capabilities}`) — w `senders.json`. `display_name` to opcjonalna, przyjazna nazwa nadawana wyłącznie w zakładce **Klienci** (Świat pokazuje ją read-only); pusta oznacza „pokaż skrócony `sender_id`”, nie jest generowana automatycznie i nigdy nie służy do adresowania. `capabilities` (`mic`/`speaker`/`text`) to trwały fakt o kliencie, symetryczny do `Device.capabilities`: World wyprowadza z nich ramowanie odpowiedzi (czy zostanie odczytana na głos) i odrzuca `speak_in_room` celujący w klienta bez głośnika. Pochodzą z handshake WS albo z rejestracji w UI — nigdy nie są wpisywane ręcznie (patrz `docs/manifest.md` sekcja 5, "Modalność to capability klienta").

### `server/voice/` — pipeline głosowy satelit

Rozłączny z `WorldEngine` (patrz sekcja 3) — zna wyłącznie opaque `sender_id`,
nigdy configu World. Wake-word to realny model `.onnx` (`OnnxWakeWordDetector`,
`Settings.wakeword_model_path`/`wakeword_threshold`, `server/config.py`), STT/TTS
to Groq (`GroqSTTProvider`) i ElevenLabs (`ElevenLabsTTSProvider`) — oba
konfigurowalne dziś przez Web UI (zakładka **Dostawcy**, pełny CRUD mirror LLM).
Pod spodem: rejestr wielu nazwanych instancji per typ (`STTRegistry`/`TTSRegistry`,
`services/server/data/{stt,tts}_backends/*.json`, mirror `BackendRegistry`
LLM) i REST CRUD `.../voice/{stt,tts}/providers*`. Dawny płaski shim
`GET/PUT /api/v1/voice/providers/config` **został usunięty** razem z
jednosslotowym formularzem, który był jego jedynym konsumentem. Puste klucze API/brak pliku modelu =
łagodna degradacja do dev-providerów (`MockSTTProvider`/`MockTTSProvider`,
`ThresholdEnergyWakeWordDetector`) — wystarczają do przetestowania całego
protokołu WS end-to-end bez żadnych kluczy (patrz
`services/server/scripts/voice_satellite_sim.py`). `voice/` nie trzyma tych
konkretów bezpośrednio, tylko singletony-routery `STTRouter`/`TTSRouter`
(`server/ai/stt`/`server/ai/tts`, patrz `docs/manifest.md` sekcja 3.5) — zmiana
klucza/modelu STT/TTS przez CRUD `.../voice/{stt,tts}/providers*` działa **od
razu, bez restartu serwera**. **Ograniczenie pozostaje wyłącznie dla
wake-word**: detektor jest budowany raz przy starcie (`main.py`,
`_build_wakeword_detector_factory`) — zmiana `Settings.wakeword_model_path`
nadal wymaga restartu.

### Prompty systemowe — World jest jedynym autorem, gdy podłączony
- **Profile promptu Świata** (`services/server/data/world/prompts/*.json`, `WorldPromptStore`): do 3 przełączalnych profili **tożsamości**, aktywny wskazuje `data/world/active_prompt.json`. W Web UI (Świat → Prompty) przełącza się je pill-tabami nad edytorem pełnej szerokości — przy trzech pozycjach właściwą kontrolką jest przełącznik, nie lista. Treść stabilna — trafia na pozycję zerową kontekstu i nie zmienia się między turami.
- **Sekcje kontekstu tury** (`services/server/data/world/prompt_sections.json`, `world/prompt_sections.py`): **uporządkowana lista** bloków tekstu wstrzykiwanych tuż przed każdym pytaniem. Kolejność listy = kolejność w prompcie. Każdy blok ma warunek pojawienia się wybierany z zamkniętej listy (`always`, `client_has_speaker`, `client_in_room` z parametrem, `has_devices`, `has_devices_in_room`, `has_groups`, `client_has_name`, …) oraz **dwa teksty**: jeden używany, gdy warunek jest spełniony, drugi gdy nie jest (pusty = przy tym wyniku sekcja nic nie dokłada). Podstawienia: `{czas}`, `{data}`, `{godzina}`, `{dzień_tygodnia}`, `{pokój}`, `{lista_pokoi}`, `{nazwa_klienta}`, `{możliwości_klienta}`, `{lista_urządzeń}`, `{urządzenia_w_pokoju}`, `{lista_grup}`. Edycja w zakładce **Świat → Kontekst tury** — dodawanie, usuwanie, przestawianie **przeciąganiem za uchwyt** (strzałki z klawiatury jako ścieżka równoważna), plus **podgląd** złożonego kontekstu dla wybranego klienta. `WorldEngine.build()` zwraca to osobno od tożsamości (`ContextBuild.turn_context`), kernel niczego nie skleja.
- **Fallback promptu kernela** (`services/server/data/agent_default_prompt.json`, `AgentDefaultPromptStore`): jedna wartość, bez CRUD — używana **wyłącznie** gdy żaden World nie jest podłączony (`NullWorldInterface`, testy headless). `DEFAULT_SYSTEM_PROMPT` w `server/agent/context/builder.py` to fallback tego fallbacku (seed przy pierwszym uruchomieniu). W normalnej pracy (World zawsze wstrzyknięty w `main.py`) to pole rzadko się uruchamia.

Najwygodniejszy sposób edycji: zakładka **Ustawienia** w Web UI, wewnątrz poziome sekcje (pills) **Agent** (dostawcy LLM, REST `/api/v1/llm/providers`, + fallbackowy prompt kernela, REST `/api/v1/agent/prompt`), **Świat** (Konfiguracja HA/pokoi/nadawców, REST `/api/v1/world/*`, + pod-zakładka **Prompty** — profile tożsamości Świata, REST `/api/v1/world/prompts/*`), **Dostawcy** (CRUD dostawców LLM/STT/TTS) i **Klienci** (rejestr klientów + progi wake-worda/VAD, REST `/api/v1/voice/*`). Zakładka **Dashboard** to wyłącznie panel powitalny/statusowy ze skrótami do sekcji Ustawień.

Zakładka **Logi** (grupa System, obok Ustawień) to panel obserwowalności potoku: lista
wywołań LLM grupowana po turze i inspektor pojedynczego wywołania. Pokazuje **dokładny
kontekst, jaki poleciał do modelu** — łącznie z system promptem i faktami tury, których
nie ma w historii czatu, bo powstają na nowo przy każdej turze i nigdzie się nie zapisują.
Każdy blok wiadomości jest opisany rolą w kontekście (`system prompt` / `fakty tury` /
`historia` / `pytanie użytkownika` / `wynik narzędzia`), a to, co się nie zmieniło od
poprzedniego wywołania tej samej sesji, jest domyślnie zwinięte — zmieniony system prompt
dostaje badge i diff liniowy. Dane pochodzą z `data/telemetry/generations.db` (patrz
`docs/manifest.md` sekcja 3.8); zakładka nie czyta `data/logs/regis.log`, który jest
osobnym, tekstowym logiem aplikacji.

---

## 3. Architektura i Relacje Pakietów Monorepo

Pełny opis architektoniczny znajduje się w dokumentu [`docs/manifest.md`](manifest.md). Struktura monorepo podzielona jest na:
- **Paczka `packages/shared`**: Dostarcza niezależne abstrakcje infrastrukturalne (logowanie `logging.py`, magistralę zdarzeń `event_bus.py`, persystencję `config.py` oraz struktury danych DTO `contracts.py`).
- **Usługa `services/server`**: Główny serwer integrujący komponenty z `shared`, udostępniający REST API v1, strumieniowanie SSE dla konsoli Web UI oraz docelową bramkę WebSockets dla architektury rozproszonej.

### Kernel i WorldEngine wewnątrz `services/server` (kluczowe dla rozbudowy):

| Warstwa | Katalog | Odpowiedzialność | Co wie o warstwie niżej |
| :--- | :--- | :--- | :--- |
| **Kernel** | `server/agent/` | LLM, pamięć, kontekst, pętla ReAct | Tylko protokół `WorldInterface` (`agent/context_provider.py`) |
| **WorldEngine** | `server/world/` | Jedyny, konkretny silnik świata (dziś: Home Assistant, przypisania nadawców do pokoi, `get_time`, `speak_in_room`) | Nic — sam orkiestruje swoje backendy wewnętrznie (dziś: `HomeAssistantClient`) |
| **Voice** | `server/voice/` | WS gateway satelit, wake-word/VAD-signaling, STT/TTS | Wyłącznie publiczny kontrakt `AgentEngine` (`start_interaction()` + `EventBus`) — **nigdy World** |
| **Telemetria** | `server/telemetry/` | Zrzut każdego wywołania LLM (kontekst, tokeny, TTFT, `finish_reason`, próby fallbacku) do SQLite | Port `BaseLLMProvider` (jest jego dekoratorem) + `LLMAttempt` z `ai/llm` — **nigdy kernel, który jej nie zna** |

**Zasada nadrzędna**: kernel nie zna z góry implementacji `WorldEngine` — ten
jest wstrzykiwany jawnie w `main.py` (`AgentEngine(world=world_engine)`),
dokładnie jak konkretny dostawca LLM. Domyślnie (bez wstrzyknięcia) kernel
używa `NullWorldInterface` — zwykły chat bez narzędzi.

Praktycznie:
- **Rozszerzanie możliwości agenta**: dziś to zwykła zmiana wewnątrz `server/world/` (nowa metoda, nowe narzędzie w `WorldEngine.build()`) — nie osobny pakiet z protokołem. Generyczna wielorozszerzeniowość została świadomie porzucona (`docs/manifest.md`, sekcja 5, "Świadome decyzje projektowe") — nie odtwarzaj jej bez konkretnego, realnego drugiego silnika świata w ręku.
- Agent adresuje urządzenia wprost przez natywny `entity_id` Home Assistant — nie ma już warstwy opaque ID (uzasadnienie: `docs/manifest.md`, sekcja 5).
- `server/voice/` i `server/world/` **nigdy się nie importują nawzajem** — jedyny wspólny mianownik to opaque `sender_id` przepływający przez kernel. `voice/` nie zna configu World (pokój), World nie zna configu voice (STT/TTS, kanał). Weryfikacja:
  ```bash
  grep -rn "from server.world" services/server/src/server/voice/
  grep -rn "from server.voice" services/server/src/server/world/
  ```
  (poprawny wynik obu: brak trafień)

---

## 4. Uruchamianie i Weryfikacja

### Uruchomienie serwera deweloperskiego:
```bash
python -m uv run --package server python -m server.main
```

> **Znane ograniczenie**: `server.main` nie eksportuje modułowego obiektu ASGI —
> aplikacja FastAPI powstaje wewnątrz asynchronicznej funkcji `main()`, po
> wcześniejszej inicjalizacji rejestru backendów, fallbackowego `AgentDefaultPromptStore` i rozszerzeń.
> Dlatego `uvicorn server.main:app --reload` kończy się błędem
> *"Attribute 'app' not found in module 'server.main'"*, a tryb hot-reload nie
> jest dostępny. Odblokowanie go wymaga zmiany w kodzie (fabryka aplikacji
> + `lifespan`), nie w dokumentacji.

### Dostępne punkty końcowe REST, SSE i Web UI:
- **Interaktywna dokumentacja Swagger UI**: `http://127.0.0.1:8000/docs`
- **Lokalny Interfejs Web UI**: `http://127.0.0.1:8000/`

> **Każdy `DELETE` zwraca ten sam kształt**: `{"success": true, "deleted_id": "<id>"}`
> (`shared.DeletionResponse`). Wcześniej było to osiem ad-hoc słowników bez
> `response_model`, i nie te same — usunięcie profilu promptu zwracało `prompt_id`
> zamiast `deleted_id`. Nieistniejący zasób to zawsze `404`, próba usunięcia zasobu
> aktywnego (dostawca, profil promptu) — `400`.

| Moduł | Metoda & Ścieżka API v1 | Opis |
| :--- | :--- | :--- |
| **System** | `GET /api/v1/health` | Status zdrowia serwera i wdrożonych modułów |
| **LLM Providers** | `GET /api/v1/llm/providers/schemas` | Pola NIEZALEŻNE od modelu (klucz API, adres serwera) — parametry generacji są per model, patrz niżej |
| | `GET /api/v1/llm/providers` | Lista presetów LLM i aktywnego ID (klucze API zamaskowane) |
| | `PUT /api/v1/llm/providers/active` | Wybór/przełączenie aktywnego presetu (globalnie — także dla satelit) |
| | `POST /api/v1/llm/providers` | Utworzenie nowego presetu (zapis JSON) |
| | `PUT /api/v1/llm/providers/{id}` | Edycja presetu (nazwa + opcje; typ niezmienny). **Pominięte pole sekretne zachowuje obecną wartość** |
| | `GET /api/v1/llm/providers/{id}/models` | Modele dostępne dla tego presetu + formularz parametrów każdego z nich. Brak klucza/padnięty serwer = 200 z polem `detail`, nie błąd |
| | `DELETE /api/v1/llm/providers/{id}` | Usunięcie presetu LLM z dysku |
| **Chat Engine** | `POST /api/v1/chat` | Synchroniczna odpowiedź Agenta w jednym zapytaniu |
| | `POST /api/v1/chat/stream` | Strumieniowanie tokenów w czasie rzeczywistym (SSE) |
| | `POST /api/v1/chat/send` | "Wyślij i zapomnij" (202) — używane przez Web UI; renderowanie idzie przez `.../watch` |
| | `POST /api/v1/chat/cancel` | Anulowanie aktywnego generowania dla podanej sesji |

Wszystkie trzy wejścia odpalające turę (`/chat`, `/chat/stream`, `/chat/send`) przechodzą przez **bramkę rejestracji**: podany `sender_id` musi być zarejestrowanym klientem, inaczej `403`. Żądanie bez `sender_id` (headless: skrypt, cron) bramki nie dotyczy. Satelity głosowe mają symetryczną bramkę w `VoiceSession` — patrz `docs/manifest.md` sekcja 5, "Bramka rejestracji".
| **Sessions** | `GET /api/v1/chat/sessions` | Pobranie podsumowań wszystkich zapisanych sesji |
| | `POST /api/v1/chat/sessions` | Utworzenie nowej sesji konwersacji |
| | `GET /api/v1/chat/sessions/{id}/history` | Pełna historia i metadane wybranej sesji |
| | `DELETE /api/v1/chat/sessions/{id}` | Trwałe usunięcie pliku i historii podanej sesji |
| **Prompts** | `GET/POST /api/v1/agent/prompts` | Lista i tworzenie promptów systemowych |
| | `GET /api/v1/agent/prompts/{id}` | Pobranie pojedynczego promptu |
| | `PUT/DELETE /api/v1/agent/prompts/{id}` | Edycja i usunięcie promptu (usunięcie aktywnego jest zablokowane) |
| | `PUT /api/v1/agent/prompts/{id}/activate` | Ustawienie promptu jako aktywnego systemowego |
| **World (Home Assistant)** | `GET/PUT /api/v1/world/config` | Odczyt (token maskowany) i zapis konfiguracji singletona (`base_url`/`access_token`) |
| | `GET /api/v1/world/catalog` | Surowy katalog wszystkich encji HA — do wyszukiwarki w UI, nie to, co widzi agent |
| | `GET /api/v1/world/areas` | Unikalne `area_id` HA wśród zadeklarowanych urządzeń — surowa podpowiedź, nigdy prawda o pokoju |
| | `GET/POST /api/v1/world/declared` | Zadeklarowana lista (to, co widzi agent) i dodanie encji po `entity_id` (opcjonalnie `room_id`) |
| | `PUT/DELETE /api/v1/world/declared/{entity_id}` | Zmiana nazwy/pokoju i usunięcie z zadeklarowanej listy |
| | `GET/POST /api/v1/world/groups` | Lista i tworzenie grup urządzeń |
| | `PUT/DELETE /api/v1/world/groups/{id}` | Edycja i usunięcie grupy |
| **World (pokoje)** | `GET/POST /api/v1/world/rooms` | Lista i tworzenie pokoi — pełnoprawny byt World, niezależny od HA Areas |
| | `PUT/DELETE /api/v1/world/rooms/{id}` | Zmiana nazwy i usunięcie pokoju (bez cascade delete przypisań) |
| | `POST /api/v1/world/rooms/import-from-ha` | Jednorazowy import pokoju per unikalna HA Area — nie ciągła synchronizacja |
| **World (kontekst tury)** | `GET/PUT /api/v1/world/prompt-sections` | Uporządkowana lista sekcji + metadane (warunki, podstawienia). PUT podmienia całą listę — kolejność to kolejność w prompcie |
| | `POST /api/v1/world/prompt-sections/reset` | Przywrócenie zestawu startowego |
| | `GET /api/v1/world/prompt-sections/preview` | Podgląd złożonego kontekstu dla `sender_id` (ta sama ścieżka co realna tura) |
| **World (nadawcy)** | `GET/POST /api/v1/world/senders` | Lista i rejestracja klienta (`sender_id -> display_name/room_id/capabilities`). POST to upsert wołany z trzech miejsc UI o różnej wiedzy o kliencie, więc **pominięte `capabilities` i `display_name` zachowują obecne**, nigdy nie czyszczą (zakładka Świat zmienia sam pokój i nie zna ani jednego, ani drugiego). Wyczyszczenie nazwy to osobna, jawna intencja: pusty string. `room_id` tej semantyki **nie** ma — tam `null` to legalne „— brak pokoju —” z pickera |
| | `DELETE /api/v1/world/senders/{sender_id}` | Usunięcie przypisania |
| **Voice (satelity)** | `WS /ws/voice/{sender_id}` | Strumień audio satelity (wake-word/VAD-signaling/STT/TTS) — patrz `shared/voice_protocol.py`. Tura kończy się albo sekwencją `tts_start`/audio/`tts_end`, albo ramką `turn_end` (nie było czego wypowiedzieć) — **zawsze jedną z nich**, bo satelita trzyma mikrofon wstrzymany do czasu powrotu do nasłuchu. Audio między `tts_start` a `tts_end` to **dowolna liczba ramek binarnych** (TTS jest strumieniowane od 2026-08-24 — pierwsza rusza, gdy tylko dostawca zwróci pierwszy fragment, nie po zakończeniu całej syntezy), nigdy jedna sklejona ramka |
| | `GET /api/v1/voice/status` | Co REALNIE działa w runtime (nie co skonfigurowano): klasy aktywnego STT/TTS/detektora wake-worda + `is_production_ready` — False także przy placeholderze wake-worda. Widoczne w Ustawieniach → Klienci |
| | `GET /api/v1/voice/stt/providers/schemas` `.../tts/providers/schemas` | Specyfikacje parametrów konfiguracji dostawców STT/TTS |
| | `GET/POST/PUT /api/v1/voice/stt/providers[/active]` `.../tts/providers[/active]` | Lista, tworzenie, edycja (`PUT .../{id}`) i przełączanie aktywnej instancji STT/TTS — pełny CRUD, mirror `/api/v1/llm/providers*`, z tą samą zasadą zachowywania pominiętych kluczy API |
| | `DELETE /api/v1/voice/stt/providers/{id}` `.../tts/providers/{id}` | Usunięcie instancji STT/TTS z dysku |
| | `GET /api/v1/voice/connected` | `sender_id` z aktualnie żywym połączeniem WS — pozwala Web UI (Świat → Nadawcy) pokazać podłączone, ale jeszcze niezarejestrowane satelity |
| **Telemetria (Logi)** | `GET /api/v1/telemetry/generations` | Lista wywołań LLM od najnowszego. Stronicowanie kursorem (`before_id`, nie offsetem — lista rośnie od góry), filtry `session_id`/`turn_id`/`status`. Wiersz **nie** niesie zrzutu wiadomości |
| | `GET /api/v1/telemetry/generations/{id}` | Pełny zrzut: dokładny kontekst wysłany do modelu (łącznie z system promptem i ulotnymi faktami tury), narzędzia, próby łańcucha fallbacku, surowa treść błędu. `404`, jeśli wpis wypadł już przez rotację |
| | `DELETE /api/v1/telemetry/generations` | Czyści całą telemetrię. Zwraca `{"success": true, "deleted": N}` — jedyny `DELETE` odbiegający od `DeletionResponse`, bo nie usuwa **zasobu o identyfikatorze**, tylko opróżnia kolekcję |

> **Świadome założenie**: `WS /ws/voice/{sender_id}` nie ma żadnego uwierzytelniania
> — spójne z resztą systemu (opaque `sender_id` bez auth, model zaufanej sieci
> lokalnej). Do rewizji dopiero przy realnej potrzebie (np. wystawienie serwera
> poza LAN).

### Test manualny pipeline'u głosowego (bez sprzętu):
Przy uruchomionym serwerze, symulator satelity przechodzi cały cykl protokołu
(handshake → wake-word → nagrywanie → `utterance_end` → odbiór TTS) bez
żadnego mikrofonu/głośnika/modelu wake-word:
```bash
python services/server/scripts/voice_satellite_sim.py [sender_id]
```
Symulator wysyła zwykłe głośne ramki PCM, więc wyzwala **wyłącznie**
placeholderowy `ThresholdEnergyWakeWordDetector` — przy skonfigurowanym
`wakeword_model_path` (realny `OnnxWakeWordDetector`) utknie na oczekiwaniu
`wake_detected`. Podany `sender_id` musi być zarejestrowanym klientem, inaczej
tura zostanie odrzucona przez bramkę rejestracji. Skrypt akceptuje obie poprawne
końcówki tury: `tts_start`/audio/`tts_end` oraz `turn_end`.

### Uruchomienie satelity desktopowej (realny mikrofon/głośnik):
Wymaga uruchomionego serwera. Klient (`services/desktop_satellite/`, patrz
`docs/manifest.md` sekcja 3.7) łączy się z `WS /ws/voice/{sender_id}`,
strumieniuje mikrofon, lokalnie wykrywa koniec wypowiedzi i odtwarza odpowiedź:
```bash
python -m uv run --package desktop_satellite python -m desktop_satellite.main
```
Bez flag: serwer rozgłasza swoją obecność w sieci lokalnej (UDP broadcast,
`server/discovery.py`/`shared/discovery.py`, port `41530`) — satelita znajduje
go automatycznie, bez ręcznego wpisywania IP. `sender_id` to trwały UUID4
wygenerowany przy pierwszym uruchomieniu i zapisany w
`services/desktop_satellite/config/settings.json` (`desktop_satellite/config.py`)
— kolejne starty używają tego samego ID. Zarejestruj wygenerowany `sender_id`
(widoczny w logu startowym) w Web UI — zakładka **Ustawienia → Klienci**, gdzie
podłączona satelita pojawia się na liście oczekujących; pokój przypisuje się jej
potem w zakładce **Świat**. Opcje `--server-url`/`--sender-id` pozwalają pominąć
auto-discovery/trwały UUID (np. inna podsieć, testy).

Wake-word wykrywa **wyłącznie serwer**, realnym modelem `.onnx` gdy skonfigurowany
(`wakeword_model_path` wyżej). STT/TTS są realne (Groq/ElevenLabs) i wymagają
wyłącznie wklejenia własnych kluczy API w zakładce **Dostawcy** — bez klucza TTS
działa łagodna degradacja do ciszy, bez klucza STT tura jest odrzucana z komunikatem
zamiast fabrykować fałszywą transkrypcję (patrz `docs/manifest.md`, sekcja 3.5).

### Uruchomienie testów:
Przed zgłoszeniem zmian obowiązkowo uruchom pełny zestaw testów (`services/server/tests/`):
```bash
python -m uv run python -m pytest -q
```

`pytest` oraz `anyio` są zadeklarowane w grupie `dev` głównego `pyproject.toml`
(PEP 735) i instalują się automatycznie przy `uv sync`. Testy asynchroniczne
używają markera `@pytest.mark.anyio` obsługiwanego przez wtyczkę pytest wbudowaną
w `anyio` — `pytest-asyncio` nie jest potrzebny.

> **Uwaga**: uruchamiaj testy przez `uv run`, a nie gołym `python -m pytest` —
> tylko wtedy masz gwarancję, że używasz środowiska workspace, a nie
> przypadkowego interpretera systemowego.

### Kontrola jakości: `ruff` i `mypy`

Oba narzędzia są w grupie `dev` i instalują się razem z resztą przy `uv sync`:

```bash
python -m uv run ruff check .
python -m uv run mypy
```

Stan oczekiwany po każdej zmianie: **ruff bez trafień, mypy bez błędów**. Oba są
skonfigurowane w głównym `pyproject.toml` w trybie raportującym, nie blokującym —
mają wskazywać dryf adnotacji i oczywiste pułapki, a nie zatrzymywać pracy na
przepisywaniu typów w kodzie, który działa. Zestaw reguł ruff jest celowo wąski
(`E4/E7/E9/F/I/B`): błędy realne, higiena importów, znane pułapki. Reguł
stylistycznych nie ma — projekt ma spójny, świadomy styl i przeformatowanie go
nie jest celem.

`ruff check . --fix` sam posortuje importy i usunie martwe; reszta wymaga decyzji.

---

## 5. Standardy Jakości Kodu i Dobre Praktyki

Obowiązujące zasady inżynierii i standardy jakości są zdefiniowane w jednym
miejscu — w pliku [**`AGENTS.md`**](../AGENTS.md) w korzeniu repozytorium
(SOLID/DRY/KISS/YAGNI/Boy Scout Rule, ścisłe typowanie, konwencja logowania
`get_logger("regis.nazwa_modułu")` oraz kierunek zależności warstw). Ten
dokument ich nie powiela — jeśli zasady mają się zmienić, zmieniaj `AGENTS.md`.

---

## 6. Cykl Pracy (Development Workflow)

Podczas prac nad projektem należy bezwzględnie stosować ustandaryzowany cykl działań:

1. **Analiza i weryfikacja faktów**:
   - Przed modyfikacją kodu sprawdź rzeczywisty stan plików, sygnatury i mechanizmy — nie zgaduj (zasada z [`AGENTS.md`](../AGENTS.md)). Dotyczy to również dokumentacji: każde zdanie w `docs/` traktuj jako hipotezę do potwierdzenia w kodzie.
2. **Implementacja i Spójność Kontraktów**:
   - Zmiany w strukturach komunikacyjnych dodawaj w `packages/shared/src/shared/contracts.py`.
   - **Respektuj kierunek zależności** (sekcja 3): kernel nie może importować z `server/world/` po nazwie — zna wyłącznie protokół `WorldInterface`. Weryfikacja:
     ```bash
     grep -rn "from server.world" services/server/src/server/agent/
     ```
     (poprawny wynik: brak trafień)
3. **Automatyczna Weryfikacja**:
   - Uruchom `python -m uv run python -m pytest -q` i upewnij się, że wszystkie testy przechodzą bez błędów.
4. **Procedura Zakończenia prac**:
   - Sprawdź zmodyfikowane pliki (`git status`).
   - Stwórz czytelny, zwięzły commit z opisem wykonanych zmian.
   - **Zapytaj o zgodę przed** `git push origin master` — wysyłka nigdy nie jest automatyczna.