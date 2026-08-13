# System Regis

**System Regis** to rozproszony system usług sieciowych komunikujących się w sieci lokalnej, zbudowany w oparciu o architekturę monorepo w języku Python z wykorzystaniem menedżera pakietów [`uv`](https://github.com/astral-sh/uv) (`uv workspace`).

Projekt oferuje elastyczne środowisko orkiestracji silnika konwersacyjnego, obsługę wielu dostawców modeli LLM (zarówno lokalnych jak Ollama, jak i chmurowych poprzez OpenRouter), asynchronizację zdarzeń w oparciu o magistralę `EventBus` oraz nowoczesny interfejs użytkownika.

---

## 🏗️ Architektura i Struktura Monorepo

System Regis podzielony jest na autonomiczne usługi (`services/`) oraz wspólne biblioteki kodu (`packages/`):

```text
Regis/
├── docs/             # Dokumentacja architektoniczna i wdrożeniowa (manifest.md, onboarding.md)
├── packages/         # Wspólne pakiety kodowe
│   └── shared/       # Paczka shared (ConfigStore, EventBus, kontrakty DTO, logowanie)
├── services/         # Usługi sieciowe i aplikacje
│   └── server/       # Główny serwer Systemu Regis (bramka REST/WS, engine, rejestr LLM, Web UI)
├── pyproject.toml    # Konfiguracja uv workspace i pytest
└── README.md         # Wprowadzenie do projektu
```

### Kluczowe Komponenty:
- **`services/server`**: Serwer sieciowy realizujący komunikację poprzez FastAPI (REST API v1), strumieniowanie odpowiedzi w czasie rzeczywistym (Server-Sent Events - SSE), silnik konwersacji (`AgentEngine`), zarządcę pamięci sesji (`MemoryManager`), budowniczy kontekstu (`ContextBuilder`) oraz wbudowany interfejs Web UI.
- **`packages/shared`**: Centralny pakiet dzielony zawierający wspólny magazyn konfiguracji (`ConfigStore`), asynchroniczną magistralę zdarzeń (`EventBus`), obiekty transferu danych (`contracts.py`) oraz standaryzowany moduł logowania (`logging.py`).

---

## 🚀 Szybki Start

### 1. Wymagania wstępne
- **Python**: `>= 3.11`
- **Menedżer pakietów**: `uv` (`pip install uv` lub instalacja z dystrybucji Astral)

### 2. Inicjalizacja środowiska
Zainstaluj zależności dla całego monorepo i powiąż pakiety workspace:
```bash
python -m uv sync
```

### 3. Uruchomienie serwera Systemu Regis
Uruchom serwer deweloperski na porcie 8000:
```bash
python -m uv run --package server uvicorn server.main:app --reload
```
Alternatywnie bezpośrednio przez moduł Python:
```bash
python -m uv run python -m server.main
```

### 4. Dostęp do Interfejsu i API
Po uruchomieniu serwera aplikacja jest dostępna pod adresami:
- **Interfejs Web UI**: `http://127.0.0.1:8000/`
- **API REST (Czat)**: `http://127.0.0.1:8000/api/v1/chat`
- **Strumieniowanie SSE**: `http://127.0.0.1:8000/api/v1/chat/stream`
- **Bramka WebSockets**: `ws://127.0.0.1:8000/ws` *(Planowana dla komunikacji wielousługowej/satelitarnej)*

---

## 🧪 Testy i Jakość Kodu

Projekt posiada automatyczny zestaw testów jednostkowych i integracyjnych uruchamianych przez `pytest`:

```bash
# Uruchomienie wszystkich testów monorepo
python -m pytest
```

---

## ⚙️ Konfiguracja Dostawców LLM

System Regis wspiera dynamiczne przełączanie backendów językowych. Instancje dostawców (Ollama, OpenRouter) są konfigurowane jako pliki JSON w `services/server/data/backends/` — najwygodniej zarządzać nimi przez zakładkę **Ustawienia** w Web UI, która korzysta z REST API `/api/v1/llm/providers`:
- **Ollama** (Domyślny lokalny): Wymaga uruchomionej instancji Ollama, adres skonfigurowany w polu `options.base_url` instancji (domyślnie `http://localhost:11434`).
- **OpenRouter** (Chmura): Wymaga klucza API ustawionego w polu `options.api_key` instancji (nie jest to zmienna środowiskowa).

Ustawienia serwera (host/port itp.) oraz instancje dostawców LLM są przechowywane w plikach JSON zarządzanych przez `ConfigStore` (`services/server/config/settings.json` oraz `services/server/data/backends/*.json`).

---

## 📚 Dokumentacja

Szczegółowe informacje znajdują się w katalogu [`docs/`](docs):
- [**`docs/onboarding.md`**](docs/onboarding.md) – Przewodnik deweloperski, konfiguracja środowiska i cykl pracy.
- [**`docs/manifest.md`**](docs/manifest.md) – Manifest Architektoniczny Systemu Regis, opisy warstw i przepływy danych.
- [**`AGENTS.md`**](AGENTS.md) – Standardy jakości i instrukcje dla agentów AI.
