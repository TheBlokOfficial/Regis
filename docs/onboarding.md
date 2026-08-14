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

### Parametry integracji (`services/server/data/plugins/smart_home/integrations/*.json`, zarządzane przez `SmartHomePlugin`):
- **`type`**: Identyfikator zarejestrowanego typu integracji (np. `HOME_ASSISTANT`).
- **`enabled`**: Czy integracja aktywnie dostarcza urządzenia agentowi (wiele integracji może być włączonych jednocześnie).
- **`options.base_url`** / **`options.access_token`**: Adres serwera Home Assistant i długoterminowy token dostępu (Long-Lived Access Token).

Grupy urządzeń (prywatna, plugin-wide konfiguracja — nie per-integracja) przechowywane są analogicznie w `services/server/data/plugins/smart_home/groups/*.json`.

### Prompty systemowe (`services/server/data/prompts/*.json`, zarządzane przez `PromptStore`):
- Treść instrukcji systemowej faktycznie wysyłanej do LLM. Aktywny prompt wskazuje `services/server/data/active_prompt.json`.
- **Uwaga**: `DEFAULT_SYSTEM_PROMPT` w `server/agent/context/builder.py` jest wyłącznie **fallbackiem i szablonem pierwszego uruchomienia**. `PromptStore.ensure_defaults()` tworzy plik tylko wtedy, gdy katalog `data/prompts/` jest pusty — późniejsza zmiana stałej w kodzie **nie zmienia** promptu, którego używa działający agent. Po rozszerzeniu możliwości agenta (np. włączeniu tool callingu) zaktualizuj aktywny prompt w zakładce **Prompty** w Web UI, inaczej model dalej będzie działał wg starych instrukcji.

Najwygodniejszy sposób edycji ustawień LLM to zakładka **Ustawienia** w Web UI (REST API `/api/v1/llm/providers`), a promptów — zakładka **Prompty** (REST API `/api/v1/agent/prompts`), a nie ręczna edycja plików JSON. Integracje na razie konfiguruje się wyłącznie przez REST (`/api/v1/integrations`) — dedykowana zakładka w Web UI jest zaplanowana.

---

## 3. Architektura i Relacje Pakietów Monorepo

Pełny opis architektoniczny znajduje się w dokumentu [`docs/manifest.md`](manifest.md). Struktura monorepo podzielona jest na:
- **Paczka `packages/shared`**: Dostarcza niezależne abstrakcje infrastrukturalne (logowanie `logging.py`, magistralę zdarzeń `event_bus.py`, persystencję `config.py` oraz struktury danych DTO `contracts.py`).
- **Usługa `services/server`**: Główny serwer integrujący komponenty z `shared`, udostępniający REST API v1, strumieniowanie SSE dla konsoli Web UI oraz docelową bramkę WebSockets dla architektury rozproszonej.

### Trzy warstwy wewnątrz `services/server` (kluczowe dla rozbudowy):

| Warstwa | Katalog | Odpowiedzialność | Co wie o warstwie niżej |
| :--- | :--- | :--- | :--- |
| **0 — Kernel** | `server/agent/` | LLM, pamięć, kontekst, pętla ReAct, `Gateway` (agregator 3 kanałów) | Tylko protokoły `PluginProvider`/`ContextProvider` |
| **1 — Pluginy** | `server/plugins/` | Domena możliwości (dziś: smart home), deklaracja narzędzi i encji | Tylko własny kontrakt (np. `DeviceIntegration`) |
| **2 — Integracje** | `server/integrations/` | Konkretne implementacje (dziś: Home Assistant) | — |

Równolegle: **Dostawcy kontekstu** (`server/context_providers/`) — kategoria obok pluginów, dostarczająca Gateway wyłącznie płaskie fakty (dziś: `DateTimeContextProvider`), nigdy narzędzi ani encji.

**Zasada nadrzędna**: żadna warstwa nie zna z góry implementacji warstwy poniżej — te rejestrują się same, jawnie, w `main.py`. Dodanie nowej integracji albo nowego pluginu **nie wymaga zmiany kernela**.

Praktycznie:
- **Nowy plugin**: klasa z polem `plugin_id: str` i metodą `async def build(facts: list[Fact]) -> PluginContribution` w `server/plugins/`, dopisana do `Gateway(plugins=[...])` w `main.py`.
- **Nowa integracja**: implementacja kontraktu pluginu (np. `DeviceIntegration`) w `server/integrations/`, eksportująca `TYPE_NAME`, `SCHEMA` i `create()`, zarejestrowana przez `plugin.register_integration_type(...)` w `main.py`. Szczegóły: [`docs/adding-integrations.md`](adding-integrations.md).
- **Nowy dostawca kontekstu**: klasa z metodą `async def get_facts() -> list[Fact]` w `server/context_providers/`, dopisana do `Gateway(context_providers=[...])` w `main.py`.
- Agent adresuje encje (urządzenia, grupy) wyłącznie przez opaque `entity_id` nadany przez Gateway — nigdy po przyjaznej nazwie ani natywnym ID integracji.

---

## 4. Uruchamianie i Weryfikacja

### Uruchomienie serwera deweloperskiego:
```bash
python -m uv run --package server python -m server.main
```

> **Znane ograniczenie**: `server.main` nie eksportuje modułowego obiektu ASGI —
> aplikacja FastAPI powstaje wewnątrz asynchronicznej funkcji `main()`, po
> wcześniejszej inicjalizacji rejestru backendów, `PromptStore` i pluginów.
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
| **Integrations** | `GET /api/v1/integrations/schemas` | Schematy pól opcji zarejestrowanych typów integracji |
| | `GET /api/v1/integrations` | Lista skonfigurowanych integracji (sekrety maskowane) |
| | `POST /api/v1/integrations` | Utworzenie nowej instancji integracji |
| | `PUT /api/v1/integrations/{id}` | Edycja instancji (w tym włączenie/wyłączenie) |
| | `DELETE /api/v1/integrations/{id}` | Usunięcie instancji integracji |
| **Device Groups** | `GET/POST /api/v1/integrations/groups` | Lista i tworzenie grup urządzeń |
| | `PUT/DELETE /api/v1/integrations/groups/{id}` | Edycja i usunięcie grupy |

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
   - **Respektuj kierunek zależności warstw** (sekcja 3): kernel nie może importować z `plugins/` ani `integrations/`, a plugin nie może importować z `integrations/` konkretnej integracji na sztywno. Weryfikacja:
     ```bash
     grep -rn "from server.plugins\|from server.integrations" services/server/src/server/agent/
     ```
     (poprawny wynik: brak trafień)
3. **Automatyczna Weryfikacja**:
   - Uruchom `python -m uv run python -m pytest -q` i upewnij się, że wszystkie testy przechodzą bez błędów.
4. **Procedura Zakończenia prac**:
   - Sprawdź zmodyfikowane pliki (`git status`).
   - Stwórz czytelny, zwięzły commit z opisem wykonanych zmian.
   - **Zapytaj o zgodę przed** `git push origin master` — wysyłka nigdy nie jest automatyczna.
