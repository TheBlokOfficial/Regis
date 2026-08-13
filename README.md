# System Regis

**System Regis** to rozproszony system usług sieciowych komunikujących się w sieci lokalnej, zbudowany w oparciu o architekturę monorepo w języku Python z wykorzystaniem menedżera pakietów [`uv`](https://github.com/astral-sh/uv) (`uv workspace`).

Regis jest **ogólnym agentem AI**: rdzeń (kernel) odpowiada za rozmowę, pamięć i pętlę agentyczną, a konkretne możliwości (dziś: sterowanie smart home) są doklejane z zewnątrz jako addony i integracje. Projekt oferuje obsługę wielu dostawców modeli LLM (lokalnych jak Ollama i chmurowych przez OpenRouter), **tool calling** w pełnej pętli ReAct, asynchroniczną magistralę zdarzeń `EventBus` oraz wbudowaną konsolę Web UI.

---

## 🏗️ Architektura i Struktura Monorepo

System Regis podzielony jest na autonomiczne usługi (`services/`) oraz wspólne biblioteki kodu (`packages/`):

```text
Regis/
├── docs/             # Dokumentacja architektoniczna i wdrożeniowa (manifest.md, onboarding.md)
├── packages/         # Wspólne pakiety kodowe
│   └── shared/       # Paczka shared (ConfigStore, EventBus, kontrakty DTO, logowanie)
├── services/         # Usługi sieciowe i aplikacje
│   └── server/       # Główny serwer Systemu Regis (bramka REST/SSE, kernel, addony, integracje, Web UI)
├── pyproject.toml    # Konfiguracja uv workspace, grupy dev i pytest
└── README.md         # Wprowadzenie do projektu
```

### Trzy warstwy wewnątrz `services/server`

Fundamentem architektury jest **kierunek zależności: żadna warstwa nie zna z góry konkretnych implementacji warstwy poniżej** — te rejestrują się same, jawnie, w kompozycji aplikacji (`main.py`).

| Warstwa | Katalog | Odpowiedzialność |
| :--- | :--- | :--- |
| **0 — Kernel** | `server/agent/` | `AgentEngine` (pętla ReAct), `MemoryManager`, `ContextBuilder`, `PromptStore`, dostawcy LLM |
| **1 — Addony** | `server/addons/` | Domena możliwości agenta i deklaracja narzędzi LLM (dziś: `SmartHomeAddon`) |
| **2 — Integracje** | `server/integrations/` | Konkretne implementacje kontraktów addonu (dziś: `HomeAssistantIntegration`) |

Dzięki temu smart home (i Home Assistant jako jedna z jego możliwych realizacji) jest tylko *narzędziem, którego agent może użyć* — nie integralną częścią tego, czym agent jest. Pełny opis warstw, przepływów danych i uzasadnienia decyzji: [`docs/manifest.md`](docs/manifest.md).

### Kluczowe komponenty:
- **`services/server`**: Serwer realizujący komunikację przez FastAPI (REST API v1), strumieniowanie odpowiedzi w czasie rzeczywistym (Server-Sent Events), silnik konwersacji `AgentEngine` z pętlą agentyczną (tool calling), zarządcę pamięci sesji `MemoryManager`, budowniczego kontekstu `ContextBuilder`, magazyn promptów systemowych `PromptStore`, addony/integracje oraz wbudowany interfejs Web UI.
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
```bash
python -m uv run --package server python -m server.main
```
Serwer startuje na porcie z `services/server/config/settings.json` (domyślnie `8000`).

> **Uwaga**: `uvicorn server.main:app` **nie zadziała** — `server.main` nie eksportuje modułowego obiektu ASGI (aplikacja powstaje wewnątrz asynchronicznej funkcji `main()`), więc tryb `--reload` nie jest obecnie dostępny.

### 4. Dostęp do Interfejsu i API
Po uruchomieniu serwera aplikacja jest dostępna pod adresami:
- **Interfejs Web UI**: `http://127.0.0.1:8000/`
- **Dokumentacja Swagger UI**: `http://127.0.0.1:8000/docs`
- **API REST (Czat)**: `http://127.0.0.1:8000/api/v1/chat`
- **Strumieniowanie SSE**: `http://127.0.0.1:8000/api/v1/chat/stream`

Pełna mapa punktów końcowych: [`docs/onboarding.md`](docs/onboarding.md#4-uruchamianie-i-weryfikacja).

---

## 🧪 Testy i Jakość Kodu

Zestaw testów (`services/server/tests/`) uruchamiany przez `pytest`, zadeklarowany w grupie `dev` głównego `pyproject.toml`:

```bash
python -m uv run python -m pytest -q
```

---

## ⚙️ Konfiguracja

Cała konfiguracja jest persystentna i trzymana w plikach JSON zarządzanych przez `ConfigStore` — **żaden parametr nie jest odczytywany ze zmiennych środowiskowych**:

| Co | Gdzie | Wygodna edycja |
| :--- | :--- | :--- |
| Ustawienia serwera (host, port, limity) | `services/server/config/settings.json` | ręcznie |
| Instancje dostawców LLM (Ollama, OpenRouter) | `services/server/data/backends/*.json` | zakładka **Ustawienia** w Web UI |
| Prompty systemowe | `services/server/data/prompts/*.json` | zakładka **Prompty** w Web UI |
| Integracje i grupy urządzeń | `services/server/data/addons/smart_home/{integrations,groups}/*.json` | REST `/api/v1/integrations` *(zakładka w Web UI: planowana)* |

Szczegółowy opis wszystkich parametrów: [`docs/onboarding.md`](docs/onboarding.md#2-konfiguracja).

---

## 📚 Dokumentacja

Szczegółowe informacje znajdują się w katalogu [`docs/`](docs):
- [**`docs/manifest.md`**](docs/manifest.md) – Manifest Architektoniczny Systemu Regis: warstwy, przepływy danych, świadome decyzje projektowe i plany rozwoju.
- [**`docs/onboarding.md`**](docs/onboarding.md) – Przewodnik deweloperski: konfiguracja środowiska, mapa API i cykl pracy.
- [**`AGENTS.md`**](AGENTS.md) – Standardy jakości i instrukcje dla agentów AI pracujących nad projektem.
