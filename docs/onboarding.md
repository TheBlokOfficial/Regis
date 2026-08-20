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
- **`wakeword_model_path`**: Ścieżka (względna wobec katalogu usługi) do wytrenowanego modelu wake-word `.onnx` (domyślnie: puste — placeholder progu amplitudy `ThresholdEnergyWakeWordDetector`, łagodna degradacja gdy plik nieskonfigurowany/nie istnieje). Model kopiuje się ręcznie, np. do `data/wakeword/<nazwa>.onnx` (katalog `data/` jest w `.gitignore`).
- **`wakeword_threshold`**: Próg pewności detekcji wake-word, 0-1 (domyślnie: `0.5` — dla konkretnego modelu użyj wartości `optimal_threshold` z jego metryk ewaluacyjnych).

### Parametry dostawców LLM (`services/server/data/backends/*.json`, zarządzane przez `BackendRegistry`):
- **`options.api_key`**: Klucz API wymagany do komunikacji z dostawcą OpenRouter (pole w instancji backendu, nie zmienna środowiskowa).
- **`options.base_url`**: Adres serwera Ollama (domyślnie: `http://localhost:11434`).

### Parametry `WorldEngine` (`services/server/data/world/config.json`, zarządzane przez `WorldEngine`):
- **`base_url`** / **`access_token`**: Adres serwera Home Assistant i długoterminowy token dostępu (Long-Lived Access Token) — pola jawne, nie schema-driven (Home Assistant jest jedynym, znanym z góry backendem silnika). Home Assistant jest traktowany jako **jeden, globalny zasób (singleton)** — jeden `base_url`/`access_token`, bez wielości nazwanych połączeń. Puste pola oznaczają brak konfiguracji — `WorldEngine` degraduje się łagodnie (encje/narzędzia HA po prostu nie są dostarczane w danej turze), bez osobnego przełącznika `enabled`.

Grupy urządzeń przechowywane są w `services/server/data/world/groups/*.json`. **Pokoje** (`Room` — pełnoprawny byt World, niezależny od Home Assistant Areas, patrz `docs/manifest.md` sekcja 5) — w `rooms/*.json`, ten sam wzorzec pliku-na-instancję co grupy. Zadeklarowana lista urządzeń widocznych dla agenta (**opt-in** — `display_name`/`room_id` per `entity_id`) — w `declared_devices.json`; brak wpisu oznacza niewidoczność, niezależnie od tego, czy encja istnieje po stronie HA. Przypisania nadawców do pokoi (`sender_id -> room_id`, **bez** kanału komunikacji ani tożsamości urządzenia — to wiedza `server/voice/`, nie World) — w `senders.json`.

### `server/voice/` — pipeline głosowy satelit

Rozłączny z `WorldEngine` (patrz sekcja 3) — zna wyłącznie opaque `sender_id`,
nigdy configu World. Wake-word to realny model `.onnx` (`OnnxWakeWordDetector`,
`Settings.wakeword_model_path`/`wakeword_threshold`, `server/config.py`), STT/TTS
to Groq (`GroqSTTProvider`) i ElevenLabs (`ElevenLabsTTSProvider`) — oba
konfigurowalne w Web UI (zakładka **Głos**, `GET/PUT /api/v1/voice/providers/config`,
`services/server/data/voice/config.json`). Puste klucze API/brak pliku modelu =
łagodna degradacja do dev-providerów (`MockSTTProvider`/`MockTTSProvider`,
`ThresholdEnergyWakeWordDetector`) — wystarczają do przetestowania całego
protokołu WS end-to-end bez żadnych kluczy (patrz
`services/server/scripts/voice_satellite_sim.py`). **Ograniczenie**: zmiana
klucza/modelu w Web UI wymaga restartu serwera, żeby zacząć obowiązywać —
providery STT/TTS/wake-word są budowane raz przy starcie (`main.py`).

### Prompty systemowe — World jest jedynym autorem, gdy podłączony
- **Profile promptu Świata** (`services/server/data/world/prompts/*.json`, `WorldPromptStore`): do 3 przełączalnych profili tożsamości, aktywny wskazuje `data/world/active_prompt.json`. `WorldEngine.build()` doklejają aktywny profil (może być pusty — domyślnie "Profil 1") do dynamicznych faktów (czas/pokój/urządzenia) i zwraca **kompletny, gotowy prompt** tej tury — kernel niczego nie skleja.
- **Fallback promptu kernela** (`services/server/data/agent_default_prompt.json`, `AgentDefaultPromptStore`): jedna wartość, bez CRUD — używana **wyłącznie** gdy żaden World nie jest podłączony (`NullWorldInterface`, testy headless). `DEFAULT_SYSTEM_PROMPT` w `server/agent/context/builder.py` to fallback tego fallbacku (seed przy pierwszym uruchomieniu). W normalnej pracy (World zawsze wstrzyknięty w `main.py`) to pole rzadko się uruchamia.

Najwygodniejszy sposób edycji: zakładka **Ustawienia** w Web UI, wewnątrz poziome sekcje (pills) **Agent** (dostawcy LLM, REST `/api/v1/llm/providers`, + fallbackowy prompt kernela, REST `/api/v1/agent/prompt`), **Świat** (Konfiguracja HA/pokoi/nadawców, REST `/api/v1/world/*`, + pod-zakładka **Prompty** — profile tożsamości Świata, REST `/api/v1/world/prompts/*`), **Głos** (status pipeline'u + config dostawców STT/TTS, REST `/api/v1/voice/status`, `/api/v1/voice/providers/config`) i **System** (info o instancji). Zakładka **Dashboard** to wyłącznie panel powitalny/statusowy ze skrótami do sekcji Ustawień.

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

| Moduł | Metoda & Ścieżka API v1 | Opis |
| :--- | :--- | :--- |
| **System** | `GET /api/v1/health` | Status zdrowia serwera i wdrożonych modułów |
| **LLM Providers** | `GET /api/v1/llm/providers/schemas` | Specyfikacje parametrów konfiguracji dostawców |
| | `GET /api/v1/llm/providers` | Lista skonfigurowanych dostawców LLM i aktywnego ID |
| | `PUT /api/v1/llm/providers/active` | Wybór/przełączenie aktywnego dostawcy LLM |
| | `POST /api/v1/llm/providers` | Utworzenie nowej instancji dostawcy (zapis JSON) |
| | `DELETE /api/v1/llm/providers/{id}` | Usunięcie konfiguracji dostawcy LLM z dysku |
| **Chat Engine** | `POST /api/v1/chat` | Synchroniczna odpowiedź Agenta w jednym zapytaniu |
| | `POST /api/v1/chat/stream` | Strumieniowanie tokenów w czasie rzeczywistym (SSE) |
| | `POST /api/v1/chat/cancel` | Anulowanie aktywnego generowania dla podanej sesji |
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
| **World (nadawcy)** | `GET/POST /api/v1/world/senders` | Lista i rejestracja przypisania nadawcy do pokoju (`sender_id -> room_id`) |
| | `DELETE /api/v1/world/senders/{sender_id}` | Usunięcie przypisania |
| **Voice (satelity)** | `WS /ws/voice/{sender_id}` | Strumień audio satelity (wake-word/VAD-signaling/STT/TTS) — patrz `shared/voice_protocol.py` |
| | `GET /api/v1/voice/status` | Status pipeline'u głosowego (nazwy klas aktywnych providerów STT/TTS/wake-word), tylko do odczytu |
| | `GET/PUT /api/v1/voice/providers/config` | Config dostawców STT/TTS (Groq/ElevenLabs) — klucze API zamaskowane na odczyt; zmiana wymaga restartu serwera |
| | `GET /api/v1/voice/connected` | `sender_id` z aktualnie żywym połączeniem WS — pozwala Web UI (Świat → Nadawcy) pokazać podłączone, ale jeszcze niezarejestrowane satelity |

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
(widoczny w logu startowym) w Web UI (zakładka **Świat → Nadawcy**), żeby
satelita miała przypisany pokój. Opcje `--server-url`/`--sender-id` pozwalają
pominąć auto-discovery/trwały UUID (np. inna podsieć, testy). Wake-word
wykrywa dziś serwer, realnym modelem `.onnx` gdy skonfigurowany
(`wakeword_model_path` wyżej), a STT/TTS to nadal dev-providerzy Mock —
realna rozmowa głosowa wymaga podłączenia docelowych dostawców chmurowych
(patrz sekcja 2, "Zaplanowane" w `manifest.md`).

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