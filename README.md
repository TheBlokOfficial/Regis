# System Regis

**System Regis** to rozproszony system usług sieciowych komunikujących się w sieci lokalnej, zbudowany w oparciu o architekturę monorepo w języku Python z wykorzystaniem menedżera pakietów [`uv`](https://github.com/astral-sh/uv) (`uv workspace`).

Regis jest **ogólnym agentem AI**: rdzeń (kernel) odpowiada za rozmowę, pamięć i pętlę agentyczną, a konkretne możliwości (dziś: sterowanie Home Assistant, data/godzina, mówienie w pokoju) dostarcza jeden, konkretny silnik świata wstrzykiwany w kompozycji aplikacji. Projekt oferuje obsługę wielu dostawców modeli LLM (lokalnie Ollama, w chmurze OpenRouter i Groq) z łańcuchem fallbacku, **tool calling** w pełnej pętli ReAct, pipeline głosowy satelit (wake-word, STT/TTS), asynchroniczną magistralę zdarzeń `EventBus` oraz wbudowaną konsolę Web UI z panelem telemetrii wywołań LLM.

---

## 🏗️ Architektura i Struktura Monorepo

System Regis podzielony jest na autonomiczne usługi (`services/`) oraz wspólne biblioteki kodu (`packages/`):

```text
Regis/
├── docs/             # Dokumentacja architektoniczna i wdrożeniowa (manifest.md, onboarding.md)
├── packages/         # Wspólne pakiety kodowe
│   └── shared/       # Paczka shared (ConfigStore, EventBus, kontrakty DTO, logowanie, korelacja tury)
├── services/         # Usługi sieciowe i aplikacje
│   ├── server/       # Główny serwer (bramka REST/SSE, kernel, silnik świata, głos, telemetria, Web UI)
│   └── desktop_satellite/  # Satelita desktopowa (mikrofon/głośnik, lokalny VAD, auto-discovery serwera)
├── pyproject.toml    # Konfiguracja uv workspace, grupy dev i pytest
└── README.md         # Wprowadzenie do projektu
```

### Warstwy wewnątrz `services/server`

Fundamentem architektury jest **kierunek zależności: kernel nie zna z góry żadnej konkretnej implementacji** — zna wyłącznie minimalne protokoły (`WorldInterface`, `BaseLLMProvider`), a konkrety wstrzykiwane są jawnie w kompozycji aplikacji (`main.py`).

| Warstwa | Katalog | Odpowiedzialność |
| :--- | :--- | :--- |
| **Porty** | `server/ports/` | Kontrakty dostawców AI: `BaseLLMProvider`, `BaseSTTProvider`, `BaseTTSProvider`, `WakeWordDetector` |
| **Kernel** | `server/agent/` | `AgentEngine`, `TurnRunner` (pętla ReAct), `MemoryManager`, `ContextBuilder` — domenowo pusty |
| **Konkrety AI** | `server/ai/` | Ollama i OpenAI-compatible (OpenRouter, Groq), STT/TTS, wake-word, rejestry i routery |
| **Silnik świata** | `server/world/` | `WorldEngine` — jedyny konkretny silnik: Home Assistant, pokoje, nadawcy, narzędzia, tożsamość agenta |
| **Głos** | `server/voice/` | Gateway WS satelit — rozłączny ze światem, zna wyłącznie `AgentEngine` |
| **Telemetria** | `server/telemetry/` | Zrzut każdego wywołania LLM (dekorator na porcie) — zasila zakładkę **Logi** |

Dzięki temu Home Assistant jest tylko *narzędziem, którego agent może użyć* — nie integralną częścią tego, czym agent jest. Generyczna wielorozszerzeniowość (`server/extensions/`, `PluginProvider`) została **świadomie porzucona**; uzasadnienie i warunki powrotu do tej decyzji: [`docs/manifest.md`](docs/manifest.md), sekcja 5.

### Kluczowe komponenty:
- **`services/server`**: Serwer realizujący komunikację przez FastAPI (REST API v1), strumieniowanie odpowiedzi w czasie rzeczywistym (Server-Sent Events), silnik konwersacji `AgentEngine` z pętlą agentyczną (tool calling), zarządcę pamięci sesji `MemoryManager`, budowniczego kontekstu `ContextBuilder`, silnik świata `WorldEngine`, pipeline głosowy satelit oraz telemetrię wywołań LLM zasilającą wbudowany interfejs Web UI.
- **`services/desktop_satellite`**: Realny klient satelity na Windows/Linux — mikrofon i głośnik przez `sounddevice`, lokalny VAD końca wypowiedzi, automatyczne odnajdywanie serwera w sieci lokalnej. Nie importuje niczego z `services/server`; łączy je wyłącznie `packages/shared` i protokół WebSocket.
- **`packages/shared`**: Centralny pakiet dzielony zawierający wspólny magazyn konfiguracji (`ConfigStore`, `JsonInstanceRepository`), asynchroniczną magistralę zdarzeń (`EventBus`), obiekty transferu danych (`contracts.py`), korelację tury (`correlation.py`), protokół WS satelit (`voice_protocol.py`) oraz standaryzowany moduł logowania (`logging.py`).

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
- **Telemetria wywołań LLM**: `http://127.0.0.1:8000/api/v1/telemetry/generations`

Pełna mapa punktów końcowych: [`docs/onboarding.md`](docs/onboarding.md#4-uruchamianie-i-weryfikacja).

---

## 🧪 Testy i Jakość Kodu

Zestaw testów (`services/server/tests/`) uruchamiany przez `pytest`, zadeklarowany w grupie `dev` głównego `pyproject.toml`:

```bash
python -m uv run python -m pytest -q
```

---

## ⚙️ Konfiguracja

Konfiguracja jest persystentna i trzymana w plikach JSON zarządzanych przez `ConfigStore`,
edytowalna w Web UI. Środowisko odpowiada wyłącznie za **wdrożenie i sekrety**:

| Zmienna | Rola |
| :--- | :--- |
| `REGIS_DATA_DIR`, `REGIS_CONFIG_DIR` | Gdzie leżą dane i konfiguracja (w kontenerze: wolumen). Bez nich: `services/server/{data,config}`. |
| `REGIS_HOST`, `REGIS_PORT`, `REGIS_DEBUG` | Nadpisania wdrożeniowe. Celowo **rozłączne** ze zbiorem pól zapisywanych z Web UI — patrz `load_settings()` w [`server/config.py`](services/server/src/server/config.py). |
| dowolna własna | Wartość klucza API lub tokenu wpisana w Web UI jako `env:NAZWA` (patrz [`shared/secrets.py`](packages/shared/src/shared/secrets.py)). Dzięki temu sekrety nie muszą leżeć w `data/`. |

Wzorzec: [`.env.example`](.env.example). Ścieżki w tabeli poniżej są względne wobec katalogu
danych; cały `data/` jest w `.gitignore`.

| Co | Gdzie | Wygodna edycja |
| :--- | :--- | :--- |
| Ustawienia serwera (host, port, limity, progi wake-word/VAD, retencja telemetrii) | `config/settings.json` | ręcznie (progi głosowe także w Ustawieniach → **Klienci**) |
| Instancje dostawców LLM (Ollama, OpenRouter, Groq) | `data/backends/*.json` + `data/active_backend.json` | Ustawienia → **Dostawcy** |
| Kolejność łańcucha fallbacku LLM | `data/fallback_chain.json` | Ustawienia → **Dostawcy** (pole `Priority` na karcie presetu) |
| Instancje dostawców STT/TTS | `data/stt_backends/*.json`, `data/tts_backends/*.json` | Ustawienia → **Dostawcy** |
| Tożsamość agenta — do 3 profili promptu | `data/world/prompts/*.json` + `data/world/active_prompt.json` | Ustawienia → **Świat → Prompty** |
| Sekcje kontekstu tury (fakty wstrzykiwane przed każdym pytaniem) | `data/world/prompt_sections.json` | Ustawienia → **Świat → Kontekst tury** |
| Połączenie z Home Assistant, zadeklarowane urządzenia, grupy, pokoje | `data/world/config.json`, `data/world/declared_devices.json`, `data/world/groups/*.json`, `data/world/rooms/*.json` | Ustawienia → **Świat** |
| Zarejestrowani klienci (`sender_id` → pokój, nazwa, możliwości) | `data/world/senders.json` | Ustawienia → **Klienci** i **Świat** |
| Historia konwersacji | `data/sessions/*.json` | zakładka **Czat** |
| Telemetria wywołań LLM | `data/telemetry/generations.db` (SQLite) | zakładka **Logi** |

> **Fallbackowy prompt kernela** (`data/agent_default_prompt.json`) to jedna wartość używana **wyłącznie** wtedy, gdy silnik świata nie jest podłączony — nie myl go z profilami tożsamości Świata z tabeli wyżej. Katalog `data/prompts/` i plik `data/active_prompt.json` to pozostałość po dawnym, wieloprofilowym magazynie promptów kernela: są nieużywane i służą już tylko jednorazowej migracji przy pierwszym starcie.

Szczegółowy opis wszystkich parametrów: [`docs/onboarding.md`](docs/onboarding.md#2-konfiguracja).

---

## 📚 Dokumentacja

Szczegółowe informacje znajdują się w katalogu [`docs/`](docs):
- [**`docs/manifest.md`**](docs/manifest.md) – Manifest Architektoniczny Systemu Regis: warstwy, przepływy danych, świadome decyzje projektowe i plany rozwoju.
- [**`docs/onboarding.md`**](docs/onboarding.md) – Przewodnik deweloperski: konfiguracja środowiska, mapa API, cykl pracy i procedura wydania.
- [**`deploy/README.md`**](deploy/README.md) – Wdrożenie produkcyjne: Docker na Raspberry Pi 5, aktualizacje, kopia zapasowa, diagnostyka.
- [**`CHANGELOG.md`**](CHANGELOG.md) – Historia wydań (wersja produktu żyje w `packages/shared/src/shared/version.py`).
- [**`AGENTS.md`**](AGENTS.md) – Standardy jakości i instrukcje dla agentów AI pracujących nad projektem.
