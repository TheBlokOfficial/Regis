# RFC: System Providerów LLM — Plan Restrukturyzacji Kodu

**Sesja:** 2026-07-31
**Status:** Gotowy do implementacji

---

## Kontekst

Architektura projektu zmieniła się z "local only" na "provider-agnostic" (patrz §5 `MANIFEST.md`).
Obecny kod ma Ollamę hard-coded jako jedyny backend LLM, routing oparty wyłącznie na tierach
węzłów i eksperymentalny `gemini_engine.py` który nie jest podłączony do żadnego przepływu.

Celem tej restrukturyzacji jest wprowadzenie warstwy abstrakcji LLM oraz dodanie OpenRouter
jako domyślnego dostawcy chmurowego — bez zmiany interfejsu dla reszty systemu.

---

## Zakres Phase 1 (priorytetowa sesja implementacyjna)

> **Ważne:** Phase 1 obejmuje wyłącznie warstwę LLM. STT i TTS pozostają bez zmian —
> nadal działają przez pipeline workerów. Pełne oddzielenie audio od workerów (cloud STT/TTS)
> jest tematem osobnej sesji (Phase 2).

**Co zmienia Phase 1:**
- Żądania **tekstowe** mogą teraz iść do chmury (OpenRouter) bez żadnego workera
- Żądania **głosowe** nadal wymagają zarejestrowanego workera (STT działa jak dotąd)
- Router przestaje używać `_TIER_PRIORITY` jako mechanizmu routingu LLM

**Co Phase 2 doda (osobna sesja):**
- `core/stt_backends/` + `core/tts_backends/` — analogiczne abstrakcje
- Split audio pipeline w Kontrolerze (cloud STT → cloud LLM → cloud TTS)
- Pełna dwustanowa degradacja z trzema komponentami (STT + LLM + TTS)
- Produkcyjny happy path bez Windowsa dla zapytań głosowych

---

## Proponowane Zmiany

### Core: Warstwa Abstrakcji LLM

#### [NEW] `src/core/llm_backends/__init__.py`
Pusty plik inicjalizujący pakiet.

#### [NEW] `src/core/llm_backends/base.py`
Abstrakcyjny interfejs `LLMBackend`. Definiuje kontrakt który muszą spełnić wszystkie implementacje:

```python
class LLMBackend(ABC):
    @abstractmethod
    def generate_response(self, messages, tools_registry, tier, **callbacks) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def get_provider_name(self) -> str: ...
```

#### [NEW] `src/core/llm_backends/ollama.py`
Lokalny backend Ollama. Ekstrahuje logikę z obecnego `llm_engine.py`:
- Deleguje do `NLUAgent` (tier `butler`) lub `ReActAgent` (tier `regis`)
- `is_available()` sprawdza czy Ollama odpowiada na `/api/tags`
- `get_provider_name()` → `"ollama"`

#### [NEW] `src/core/llm_backends/openrouter.py`
Chmurowy backend OpenRouter. Punkt startowy: istniejący `gemini_engine.py`, z następującymi zmianami:
- URL: `https://openrouter.ai/api/v1/chat/completions`
- Klucz: `OPENROUTER_API_KEY` z `.env` Kontrolera
- Model: `OPENROUTER_MODEL` z `.env` (bez hardcode — model jest decyzją operacyjną)
- `is_available()` sprawdza czy klucz API jest skonfigurowany i niepusty
- `get_provider_name()` → `"openrouter"`
- Musi zachować **streaming** (SSE) — OpenRouter obsługuje OpenAI-compatible streaming

#### [MODIFY] `src/core/llm_engine.py`
Staje się fabryką/selektorem — nie zawiera już logiki Ollamy, tylko tworzy właściwy backend.
Zachowuje wsteczną kompatybilność sygnatury `generate_response()` jako fasada.

```python
def get_llm_backend(tier: str) -> LLMBackend:
    """Zwraca najlepszy dostępny backend wg priorytetu: cloud > local."""
    ...
```

#### [DELETE] `src/core/gemini_engine.py`
Logika migruje do `llm_backends/openrouter.py`. Plik do usunięcia po weryfikacji.

---

### Controller: Routing oparty na Providerach

#### [NEW] `src/controller/providers.py`
Nowy moduł zarządzający dostępnością providerów LLM. Główna odpowiedzialność:

```python
def get_llm_backend() -> LLMBackend | None:
    """Zwraca najlepszy dostępny backend LLM lub None jeśli żaden nie działa.
    Priorytet: OpenRouter (cloud) > Ollama worker (local)
    """
    ...

def has_llm_provider() -> bool: ...

# Phase 2 doda:
# def has_stt_provider() -> bool: ...
# def has_tts_provider() -> bool: ...
# def is_full_mode() -> bool:  # wszystkie 3 komponenty mają provider
```

#### [MODIFY] `src/controller/registry.py`
- **Usunąć:** `_TIER_PRIORITY = {"regis": 2, "butler": 1}` jako mechanizm routingu
- **Zachować:** pole `tier` w rejestracji workera — nadal używane do wyboru promptu (`tier_butler.md` vs `tier_regis.md`), nie do routingu
- **Usunąć lub przepisać:** `_pick_worker()` — logika przenosi się do `providers.py`
- **Zachować:** wszystko inne (rejestracja, heartbeat, satelity)

> **Uwaga:** Tier w schemacie rejestracji nie znika z kodu. Pozostaje jako informacja
> o trybie promptu modelu. Usuwa się tylko powiązanie tier → priorytet routingu.

#### [MODIFY] `src/controller/router.py`
Najważniejsza zmiana funkcjonalna. Przepływ `_proxy_sse_to_queue()` zmienia się:

```
# Przed:
workers = sorted(worker_registry, by=_TIER_PRIORITY)
→ wyślij do najlepszego workera

# Po (Phase 1):
backend = providers.get_llm_backend()

if backend is None:
    → błąd: "Brak dostępnego providera LLM."
elif isinstance(backend, OpenRouterBackend):
    → wywołaj cloud LLM bezpośrednio (żądania tekstowe)
    → dla żądań głosowych: nadal wymagaj workera (STT niezmienione)
else:  # OllamaBackend
    → wyślij do zarejestrowanego workera (dotychczasowy flow)
```

Dodatkowo — **usunąć hardcoded komunikaty:**
- `"Awaryjny węzeł na Malince (Butler) nie zgłosił gotowości"`
- `"Sprawdź status regis-worker.service"`
- Zastąpić ogólnymi: `"Brak dostępnego providera LLM."`

---

### Konfiguracja

#### [MODIFY] `.env.example`
Dodać nowe klucze:

```env
# OpenRouter (cloud LLM provider) — konfigurowany na Kontrolerze (RPi5)
OPENROUTER_API_KEY=
OPENROUTER_MODEL=

# Ollama (lokalny LLM provider — opcjonalny, Windows Node)
# OLLAMA_URL=http://127.0.0.1:11434
```

#### Gdzie konfigurować klucz OpenRouter?

Klucz `OPENROUTER_API_KEY` idzie wyłącznie w `.env` **Kontrolera (RPi5)** — bo to
Kontroler bezpośrednio wywołuje cloud API (Opcja B z MANIFEST §3). Windows Node nie
potrzebuje tego klucza: jego worker używa lokalnej Ollamy, a Kontroler i tak agreguje wyniki.

| Instancja | `OPENROUTER_API_KEY` | `OLLAMA_URL` |
|---|---|---|
| RPi5 (Kontroler) | TAK — wymagany do cloud LLM | nie dotyczy |
| Windows Node (Worker) | NIE | TAK — Ollama lokalna |

#### [MODIFY] `src/core/config.py`
- Dodać ładowanie `OPENROUTER_API_KEY` i `OPENROUTER_MODEL` ze zmiennych środowiskowych
- Przy okazji: usunąć dead code `if getattr(sys, 'frozen', False)` (dług techniczny z §7 MANIFEST)

---

## Co Pozostaje Bez Zmian

| Plik | Status |
|---|---|
| `core/agents/nlu_agent.py` | Bez zmian |
| `core/agents/react_agent.py` | Bez zmian |
| `core/stream_parser.py` | Bez zmian |
| `core/stt_engine.py` | Bez zmian (Phase 2) |
| `core/tts_engine.py` | Bez zmian (Phase 2) |
| `core/tools_registry.py` | Bez zmian |
| `core/schemas.py` | Bez zmian |
| `integrations/` | Bez zmian |
| `controller/worker/server.py` | Bez zmian |
| `node/worker.py` | Bez zmian |
| `node/satellite.py` | Bez zmian |

---

## Mapa Zależności — Kolejność Implementacji

```
1. core/llm_backends/base.py          <- żadnych zależności
2. core/llm_backends/ollama.py        <- zależy od base.py, nlu_agent, react_agent
3. core/llm_backends/openrouter.py    <- zależy od base.py
4. core/llm_engine.py (refactor)      <- zależy od llm_backends/
5. core/config.py (update)            <- niezależne
6. controller/providers.py            <- zależy od llm_backends/, registry
7. controller/registry.py (update)    <- usuwa _TIER_PRIORITY
8. controller/router.py (update)      <- zależy od providers.py
9. .env.example (update)              <- niezależne
10. DELETE gemini_engine.py           <- po weryfikacji że openrouter.py działa
```

---

## Plan Testów

### Testy jednostkowe (pytest)
Nowy plik: `tests/test_llm_backends.py` — mockowane wywołania API:
- `OllamaBackend.is_available()` gdy Ollama nie działa → `False`
- `OpenRouterBackend.is_available()` gdy brak klucza → `False`
- `get_llm_backend()` z kluczem skonfigurowanym → zwraca `OpenRouterBackend`
- `get_llm_backend()` bez klucza, z workerem → zwraca `OllamaBackend`
- `get_llm_backend()` bez klucza, bez workera → `None`

### Weryfikacja manualna
1. Uruchomić Kontroler z `OPENROUTER_API_KEY` ustawionym, bez żadnego workera
2. Wysłać zapytanie tekstowe przez Dashboard
3. Sprawdzić w logach: `"Provider: openrouter"` zamiast `"Routowanie do węzła"`
4. Odpowiedź powinna przyjść z chmury

---

## Uwagi Implementacyjne

**Streaming z OpenRouter:** Obecny flow SSE zakłada że Worker streamuje odpowiedź.
OpenRouter obsługuje streaming przez OpenAI-compatible API (parametr `stream: true`).
Implementacja `openrouter.py` musi zachować streaming — nie blokować na pełną odpowiedź.

**Koszty i monitoring:** OpenRouter zwraca `usage` (liczba tokenów) w każdej odpowiedzi.
Warto to zalogować (DEBUG) dla monitorowania kosztów. Niekonieczne dla MVP.

**Istniejący `gemini_engine.py`:** To dobry punkt startowy dla `openrouter.py` — już
używa OpenAI-compatible API. Różnica to tylko URL i klucz. Nie reużywaj go bezpośrednio —
skopiuj logikę do nowego pliku i usuń oryginał.
