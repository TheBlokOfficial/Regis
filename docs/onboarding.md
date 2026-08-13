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

## 2. Konfiguracja i Zmienne Środowiskowe

System Regis obsługuje zarówno dostawców lokalnych, jak i chmurowych. Ustawienia zarządzane są persystentnie przez moduł `ConfigStore` (`packages/shared/src/shared/config.py`), zapisywane w pliku `services/server/config/settings.json`.

### Parametry konfiguracyjne:
- **`OPENROUTER_API_KEY`**: Klucz API wymagany do komunikacji z dostawcą OpenRouter (opcjonalny, jeśli używany jest tylko Ollama).
- **`OLLAMA_BASE_URL`**: Adres serwera Ollama (domyślnie: `http://localhost:11434`).
- **`SERVER_HOST`**: Adres nasłuchiwania interfejsu sieciowego (domyślnie: `0.0.0.0` / `127.0.0.1`).
- **`SERVER_PORT`**: Port serwera HTTP/WebSocket (domyślnie: `8000`).

---

## 3. Architektura i Relacje Pakietów Monorepo

Pełny opis architektoniczny znajduje się w dokumentu [`docs/manifest.md`](file:///d:/Projekty/Regis/docs/manifest.md). Struktura monorepo podzielona jest na:
- **Paczka `packages/shared`**: Dostarcza niezależne abstrakcje infrastrukturalne (logowanie `logging.py`, magistralę zdarzeń `event_bus.py`, persystencję `config.py` oraz struktury danych DTO `contracts.py`).
- **Usługa `services/server`**: Główny serwer integrujący komponenty z `shared`, udostępniający REST API v1, strumieniowanie SSE dla konsoli Web UI oraz docelową bramkę WebSockets dla architektury rozproszonej.

---

## 4. Uruchamianie i Weryfikacja

### Uruchomienie serwera deweloperskiego:
```bash
python -m uv run --package server uvicorn server.main:app --reload
```

### Dostępne punkty końcowe API v1:
- **Lokalny Interfejs Web UI**: `http://127.0.0.1:8000/`
- **REST API Chat**: `POST http://127.0.0.1:8000/api/v1/chat`
- **SSE Streaming Chat**: `POST http://127.0.0.1:8000/api/v1/chat/stream`
- **Anulowanie aktywnego zapytania**: `POST http://127.0.0.1:8000/api/v1/chat/cancel`
- **Lista i historia sesji**: `GET http://127.0.0.1:8000/api/v1/chat/sessions`
- **Bramka WebSocket**: `ws://127.0.0.1:8000/ws` *(Planowana dla komunikacji rozproszonej)*

### Uruchomienie testów:
Przed zgłoszeniem zmian obowiązkowo uruchom pełny zestaw testów:
```bash
python -m pytest
```

---

## 5. Standardy Jakości Kodu i Dobre Praktyki

Wszystkie zasady inżynierii oprogramowania oraz standardy jakości obowiązujące w projekcie są szczegółowo zdefiniowane w pliku [**`AGENTS.md`**](file:///d:/Projekty/Regis/AGENTS.md). 

Najważniejsze filary:
1. **Zasady SOLID, DRY, KISS, POLA & Boy Scout Rule**: Twórz kod modułowy, czytelny i bez niepotrzebnego powielania logiki.
2. **Ścisłe Typowanie (Strict Type Hints)**: Wszystkie sygnatury funkcji i metod muszą posiadać pełne adnotacje typów Python.
3. **Ujednolicone Logowanie**: Używaj ustandaryzowanego logera: `logger = get_logger("regis.nazwa_modułu")`.

---

## 6. Cykl Pracy (Development Workflow)

Podczas prac nad projektem należy bezwzględnie stosować ustandaryzowany cykl działań:

1. **Analiza i weryfikacja faktów (Chain of Thought)**:
   - Przed modyfikacją kodu sprawdź rzeczywisty stan plików, sygnatury i mechanizmy. Wykonaj pełną analizę COT zgodnie z wytycznymi z [`AGENTS.md`](file:///d:/Projekty/Regis/AGENTS.md).
2. **Implementacja i Spójność Kontraktów**:
   - Zmiany w strukturach komunikacyjnych dodawaj w `packages/shared/src/shared/contracts.py`.
3. **Automatyczna Weryfikacja**:
   - Uruchom `python -m pytest` i upewnij się, że wszystkie testy przechodzą bez błędów.
4. **Procedura Zakończenia prac**:
   - Sprawdź zmodyfikowane pliki (`git status`).
   - Stwórz czytelny, zwięzły commit z opisem wykonanych zmian.
   - Wykonaj wysyłkę zmian do repozytorium GitHub (`git push origin master`).
