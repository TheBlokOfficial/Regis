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

### Parametry dostawców LLM (`services/server/data/backends/*.json`, zarządzane przez `BackendRegistry`):
- **`options.api_key`**: Klucz API wymagany do komunikacji z dostawcą OpenRouter (pole w instancji backendu, nie zmienna środowiskowa).
- **`options.base_url`**: Adres serwera Ollama (domyślnie: `http://localhost:11434`).

### Parametry `WorldEngine` (`services/server/data/world/config.json`, zarządzane przez `WorldEngine`):
- **`base_url`** / **`access_token`**: Adres serwera Home Assistant i długoterminowy token dostępu (Long-Lived Access Token) — pola jawne, nie schema-driven (Home Assistant jest jedynym, znanym z góry backendem silnika). Home Assistant jest traktowany jako **jeden, globalny zasób (singleton)** — jeden `base_url`/`access_token`, bez wielości nazwanych połączeń. Puste pola oznaczają brak konfiguracji — `WorldEngine` degraduje się łagodnie (encje/narzędzia HA po prostu nie są dostarczane w danej turze), bez osobnego przełącznika `enabled`.

Grupy urządzeń przechowywane są w `services/server/data/world/groups/*.json`. Zadeklarowana lista urządzeń widocznych dla agenta (**opt-in** — `display_name` per `entity_id`) — w `declared_devices.json`; brak wpisu oznacza niewidoczność, niezależnie od tego, czy encja istnieje po stronie HA. Rejestr satelit (`sender_id -> pokój/kanał komunikacji`) — w `satellites.json`.

### Prompty systemowe (`services/server/data/prompts/*.json`, zarządzane przez `PromptStore`):
- Treść instrukcji systemowej faktycznie wysyłanej do LLM. Aktywny prompt wskazuje `services/server/data/active_prompt.json`.
- **Uwaga**: `DEFAULT_SYSTEM_PROMPT` w `server/agent/context/builder.py` jest wyłącznie **fallbackiem i szablonem pierwszego uruchomienia**. `PromptStore.ensure_defaults()` tworzy plik tylko wtedy, gdy katalog `data/prompts/` jest pusty — późniejsza zmiana stałej w kodzie **nie zmienia** promptu, którego używa działający agent. Po rozszerzeniu możliwości agenta (np. włączeniu tool callingu) zaktualizuj aktywny prompt w zakładce **Prompty** w Web UI, inaczej model dalej będzie działał wg starych instrukcji.

Najwygodniejszy sposób edycji ustawień LLM to zakładka **Ustawienia** w Web UI (REST API `/api/v1/llm/providers`), promptów — zakładka **Prompty** (REST API `/api/v1/agent/prompts`), a Home Assistant/satelit — zakładka **Rozszerzenia** (REST API `/api/v1/world/*`), a nie ręczna edycja plików JSON.

---

## 3. Architektura i Relacje Pakietów Monorepo

Pełny opis architektoniczny znajduje się w dokumentu [`docs/manifest.md`](manifest.md). Struktura monorepo podzielona jest na:
- **Paczka `packages/shared`**: Dostarcza niezależne abstrakcje infrastrukturalne (logowanie `logging.py`, magistralę zdarzeń `event_bus.py`, persystencję `config.py` oraz struktury danych DTO `contracts.py`).
- **Usługa `services/server`**: Główny serwer integrujący komponenty z `shared`, udostępniający REST API v1, strumieniowanie SSE dla konsoli Web UI oraz docelową bramkę WebSockets dla architektury rozproszonej.

### Kernel i WorldEngine wewnątrz `services/server` (kluczowe dla rozbudowy):

| Warstwa | Katalog | Odpowiedzialność | Co wie o warstwie niżej |
| :--- | :--- | :--- | :--- |
| **Kernel** | `server/agent/` | LLM, pamięć, kontekst, pętla ReAct | Tylko protokół `WorldInterface` (`agent/context_provider.py`) |
| **WorldEngine** | `server/world/` | Jedyny, konkretny silnik świata (dziś: Home Assistant, satelity, `get_time`) | Nic — sam orkiestruje swoje backendy wewnętrznie (dziś: `HomeAssistantClient`) |

**Zasada nadrzędna**: kernel nie zna z góry implementacji `WorldEngine` — ten
jest wstrzykiwany jawnie w `main.py` (`AgentEngine(world=world_engine)`),
dokładnie jak konkretny dostawca LLM. Domyślnie (bez wstrzyknięcia) kernel
używa `NullWorldInterface` — zwykły chat bez narzędzi.

Praktycznie:
- **Rozszerzanie możliwości agenta**: dziś to zwykła zmiana wewnątrz `server/world/` (nowa metoda, nowe narzędzie w `WorldEngine.build()`) — nie osobny pakiet z protokołem. Generyczna wielorozszerzeniowość została świadomie porzucona (`docs/manifest.md`, sekcja 5, "Świadome decyzje projektowe") — nie odtwarzaj jej bez konkretnego, realnego drugiego silnika świata w ręku.
- Agent adresuje urządzenia wprost przez natywny `entity_id` Home Assistant — nie ma już warstwy opaque ID (uzasadnienie: `docs/manifest.md`, sekcja 5).

---

## 4. Uruchamianie i Weryfikacja

### Uruchomienie serwera deweloperskiego:
```bash
python -m uv run --package server python -m server.main
```

> **Znane ograniczenie**: `server.main` nie eksportuje modułowego obiektu ASGI —
> aplikacja FastAPI powstaje wewnątrz asynchronicznej funkcji `main()`, po
> wcześniejszej inicjalizacji rejestru backendów, `PromptStore` i rozszerzeń.
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
| | `GET /api/v1/world/areas` | Unikalne `area_id` wśród zadeklarowanych urządzeń — wygoda formularza rejestracji satelity |
| | `GET/POST /api/v1/world/declared` | Zadeklarowana lista (to, co widzi agent) i dodanie encji po `entity_id` |
| | `PUT/DELETE /api/v1/world/declared/{entity_id}` | Zmiana nazwy i usunięcie z zadeklarowanej listy |
| | `GET/POST /api/v1/world/groups` | Lista i tworzenie grup urządzeń |
| | `PUT/DELETE /api/v1/world/groups/{id}` | Edycja i usunięcie grupy |
| **World (satelity)** | `GET/POST /api/v1/world/satellites` | Lista i rejestracja satelity (`sender_id -> pokój/kanał`) |
| | `DELETE /api/v1/world/satellites/{sender_id}` | Usunięcie rejestracji satelity |

> **Planowane, jeszcze nieistniejące**: bramka WebSocket (`ws://127.0.0.1:8000/ws`)
> dla komunikacji rozproszonej. W kodzie nie ma dziś żadnego endpointu WS —
> `gateway.py` rejestruje wyłącznie router REST/SSE i montuje SPA.

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