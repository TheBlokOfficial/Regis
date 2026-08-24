# Audyt architektoniczny i plan refaktoryzacji — System Regis

**Data:** 2026-08-24 · **Zakres:** całe repozytorium (`packages/shared`, `services/server`, `services/desktop_satellite`, Web UI)
**Stan wyjściowy:** `master` @ `f864004`, 209 testów zielonych, brak zmian w kodzie źródłowym podczas audytu.

> Dokument **efemeryczny** — po wdrożeniu planu jego trwała treść przenosi się do `docs/manifest.md`
> / `docs/onboarding.md`, a plik znika (reguła z `AGENTS.md`, sekcja „Dokumentacja"). Nie jest to
> `docs/specs/*.md`, bo opisuje przebudowę wielu obszarów naraz, a nie jedną funkcjonalność.

---

## STATUS — 2026-08-24

**Wdrożone: E0-E7** (osiem commitów, `7fc882e`..`690754e`). Testy 209 → **229**,
`ruff` bez trafień, `mypy` bez błędów na 104 plikach, serwer zweryfikowany na żywo.

| Etap | Stan | Dowód weryfikacji |
| :-- | :-- | :--- |
| E0 narzędzia jakości | ✅ | baza doprowadzona do zera |
| E1 naprawa F1 + martwy kod | ✅ | test regresyjny na prawdziwym rejestrze |
| E2 `server/ports/` | ✅ | oba cykle: 0 trafień grep-em |
| E3 wspólny magazyn instancji | ✅ | round-trip na kopii realnych danych: 0 zmienionych plików |
| E4 jedna logika CRUD dostawców | ✅ | diff OpenAPI + pełny przebieg CRUD przez `TestClient` |
| E5 rozbicie `WorldEngine` | ✅ | złoty wzorzec `build()`: prompt tury bajt w bajt |
| E6 rozbicie routera World | ✅ | 65 operacji → 65, zero zmian kodów odpowiedzi |
| E7 rozbicie `AgentEngine` | ✅ | złoty wzorzec tury: 14 zdarzeń + `metadata` bajt w bajt |
| **E8 voice: kodek ramek + obecność klienta** | ⬜ | — |
| **E9 Web UI** | ⬜ | — |
| E10 dokumentacja | 🟡 | `manifest.md`/`onboarding.md`/`AGENTS.md` zaktualizowane dla E0-E7 |

**Bilans E0-E7** — liczby netto, żeby nie wprowadzały w błąd:

| | zmiana |
| :--- | ---: |
| Linie **wykonywalne** kodu produkcyjnego | 6212 → 6278 (**+66**, +1%) |
| Komentarze i docstringi | 1887 → 2293 (+406) |
| Plików `.py` (produkcyjnych) | 82 → 104, średnio 98 → 82 linii |
| Plików > 500 linii | 2 → 1 (największy: 734 → 554) |
| Kopii magazynu instancji / routera CRUD | 6 → 1 / 3 → 1 |
| Cykli zależności między pakietami | 2 → 0 |

Kod wykonywalny jest **praktycznie płaski**: usunięta duplikacja została niemal
dokładnie zjedzona przez dodane abstrakcje. Zysk nie jest w objętości, tylko
w liczbie miejsc, które trzeba edytować przy jednej zmianie, i w klasie błędów,
która zniknęła razem z kopiami (dwa z trzech naprawionych błędów wynikały
bezpośrednio z tego, że kod istniał w kilku egzemplarzach).

**Trzy błędy naprawione po drodze:**

1. **F1** — edycja aktywnego presetu LLM nie działała do restartu serwera (E1).
2. Halucynowana nazwa narzędzia trafiała do egzekutora Home Assistant, który
   odpowiadał „Nie znaleziono pasującej encji" zamiast „nie ma takiego narzędzia" (E5).
3. Każda nieudana tura zostawiała `Task exception was never retrieved` w logach,
   opisujący błąd, który system właśnie w pełni obsłużył (E7).

**Dwie świadome zmiany widoczne dla użytkownika:** wspólny komunikat przy próbie
usunięcia aktywnego dostawcy (zamiast trzech wariantów tego samego zdania) oraz
`DELETE /world/prompts/{id}` zwracające `deleted_id` zamiast `prompt_id`
(ujednolicone z pozostałymi siedmioma; Web UI nie czyta żadnego z tych pól).

**Decyzje D1-D4 rozstrzygnięte:** D1 tak (`ports/`), D2 tak (konsolidacja rejestrów),
D3 usunąć (`check_health`), **D4 nie** — bez `vitest`/Node; projekt zostaje czysto
pythonowy, a czysta logika z `step_rail.js` ma zostać wydzielona tak, żeby dało się
ją otestować później, gdyby decyzja się zmieniła.

Poniższy audyt i plan zostają w niezmienionej formie jako opis stanu wyjściowego
i zakresu E8-E9. **Po ich wdrożeniu ten plik znika** — trwała treść idzie do
`docs/manifest.md`/`docs/onboarding.md` (reguła z `AGENTS.md`, sekcja „Dokumentacja").

## 0. Streszczenie

**Werdykt: architektura jest zdrowa na poziomie granic, a uciążliwa na poziomie ziarnistości.**

Twoje dwie hipotezy wyjściowe sprawdziłem wprost w kodzie:

| Hipoteza | Werdykt | Uzasadnienie |
| :--- | :--- | :--- |
| **1. Wyciekający kod niskopoziomowy** (nagłówki HTTP, parsowanie odpowiedzi dostawców, buforowanie audio w plikach orkiestracji) | **W większości NIEPRAWDZIWA** | `agent/engine.py` nie zna ani jednego szczegółu API dostawcy — akumulacja fragmentarycznych `delta.tool_calls` siedzi w `ai/llm/providers/openai_compatible.py`, nagłówki HA w `world/client.py`, strumień PCM w `voice/session.py` operuje już na gotowych fragmentach z `synthesize_stream()`. Interfejsy są dokładnie tak cienkie, jak chcesz: `stt.transcribe(pcm)`, `tts.synthesize_stream(text)`, `llm.generate_stream(messages, tools)`. **Trzy realne wyjątki** — patrz F7, F8, F9. |
| **2. Naruszenia SRP / sztucznie spłaszczone katalogi** | **PRAWDZIWA** | `world/` i `voice/` mieszają w jednym poziomie trasy HTTP, logikę domenową, DTO i klientów zewnętrznych. `world/engine.py` (734 linie) łączy 5 niezależnych magazynów danych z budową promptu tury. `world/routes.py` (390 linii) obsługuje 8 rodzin zasobów. |

Do tego doszło **jedno realne znalezisko funkcjonalne** (nie strukturalne): edycja aktywnego presetu LLM
nie działa do restartu serwera — **F1**, potwierdzone uruchomionym testem, nie wywnioskowane.

Największym realnym kosztem nawigacyjnym nie są jednak „god objecty", tylko **potrojony kod**:
trzy niemal identyczne rejestry backendów, trzy niemal identyczne routery CRUD dostawców,
sześćdziesiąt metod delegujących w `api_client.js` i sześćdziesiąt pięć kopii bloku `try/fetch/!ok/catch`.
Zmiana jednego pojęcia wymaga dziś edycji od trzech do sześciu plików — i to jest ta „uciążliwość",
którą odczuwasz przy dalszym rozwoju.

**Liczby:**

| Obszar | Pliki | Linie | Największy plik |
| :--- | ---: | ---: | :--- |
| Python (kod produkcyjny) | 55 | ~8 700 | `world/engine.py` — 734 |
| Python (testy) | 24 | ~5 700 | `test_voice_pipeline.py` — 517 |
| JavaScript (Web UI) | 33 | 7 046 | `views/chat/step_rail.js` — 782 |
| CSS | 23 | 4 138 | `views/extensions.css` — 610 |

---

## 1. Mapa przepływów i zależności

### 1.1 Kierunek zależności — stan faktyczny (zweryfikowany grep-em)

```text
                        ┌───────────────┐
                        │   main.py     │  kompozycja: jedyne miejsce znające wszystkich
                        └───────┬───────┘
             ┌──────────────────┼──────────────────┬─────────────────┐
             v                  v                  v                 v
       ┌──────────┐      ┌────────────┐     ┌───────────┐     ┌───────────┐
       │  agent/  │<─────│   world/   │     │  voice/   │────>│    ai/    │
       │ (kernel) │      │ (silnik    │     │ (satelity)│<────│ (adaptery)│
       └────┬─────┘      │  świata)   │     └─────┬─────┘     └─────┬─────┘
            │  ▲         └────────────┘           │                 │
            │  └──────────────────────────────────┴─────────────────┘
            │                    (agent/llm.py, voice/stt.py, voice/tts.py)
            v
       ┌──────────┐
       │ network/ │  ──> montuje routery world/ i voice/
       └──────────┘
```

**Cztery granice trzymają się bez zarzutu** — grep daje zero trafień we wszystkich kierunkach
deklarowanych w `AGENTS.md` i `docs/manifest.md`:

```bash
grep -rn "from server.world" services/server/src/server/agent/   # 0
grep -rn "from server.voice" services/server/src/server/agent/   # 0
grep -rn "from server.world" services/server/src/server/voice/   # 0
grep -rn "from server.voice" services/server/src/server/world/   # 0
```

**Dwie granice są złamane** i utrzymywane przy życiu leniwymi importami — to jest **F2**:

```bash
grep -rn "from server.voice" services/server/src/server/ai/   # 10 trafień (ai -> voice)
grep -rn "from server.ai"    services/server/src/server/voice/ #  2 trafienia (voice -> ai)
```

### 1.2 Przepływ tury agenta (ReAct)

```text
  wejście                 kernel                        świat                dostawca
 ─────────               ────────                      ───────              ──────────
POST /chat/send ──┐
WS utterance_end ─┴─> start_interaction()
                        │
                        ├─ memory.add_message(user)  ────────────────────────> data/sessions/*.json
                        ├─ publish CHAT_USER_MESSAGE ──> EventBus
                        ├─ world.build(sender_id) ─────> WorldEngine.build()
                        │                                 ├─ list_rooms/get_senders   (dysk)
                        │                                 ├─ resolve_devices          (HTTP -> HA)
                        │                                 ├─ render sekcji kontekstu  (prompt_sections)
                        │                                 └─> ContextBuild{tools, system_prompt,
                        │                                                  turn_context, dispatch}
                        ├─ context_builder.build_messages()
                        │
                        └─ PĘTLA (max 8 iteracji):
                             llm.generate_stream(msgs, tools) ──────────────> LLMRouter -> konkret
                               ├─ str            -> bufor + publish CHAT_CHUNK{kind:"answer"}
                               ├─ ReasoningChunk -> publish CHAT_CHUNK{kind:"reasoning"}
                               └─ ToolCallRequest-> dispatch() -> ToolResult
                                                     └─ redirect_sender_id? -> zmiana target_client_id
                             publish CHAT_DONE / CHAT_ERROR / CHAT_CANCELLED
```

Odbiorcy zdarzeń są od siebie niezależni i filtrują po **dwóch różnych identyfikatorach**:

| Odbiorca | Filtruje po | Skutek |
| :--- | :--- | :--- |
| `interact_stream()` / `watch_session()` (SSE, Web UI) | `session_id` | widzi całą turę, także przekierowaną |
| `VoiceConnection` (`voice/gateway.py`) | `target_client_id` | mówi tylko to, co zaadresowano do niego |

### 1.3 Przepływ tury głosowej (satelita)

```text
 desktop_satellite                    server/voice                     kernel
 ─────────────────                    ────────────                     ──────
 mic -> PCM 20ms  ──WS bin──>  VoiceSession.handle_audio_frame()
                                 └─ wakeword.process(chunk)  [~20ms CPU, co ~320ms]
                          <──WS json── wake_detected
 play_cue("Speech On")
 vad.process()   ──WS json──>  handle_utterance_end()
                                 ├─ bramka is_registered()  -> 403-odpowiednik
                                 └─ stt.transcribe(bufor) ──> Groq
                                     └─ on_transcript() ─────────────> start_interaction()
                                                                          (patrz 1.2)
                              _on_done (EventBus, target_client_id)
                                 └─ session.speak(text)  [zadanie w tle, NIE w handlerze]
                          <──WS json── tts_start
                          <──WS bin ── N ramek PCM      <── tts.synthesize_stream()
                          <──WS json── tts_end
 stop_stream() ──WS json──>  handle_playback_done() -> LISTENING_WAKEWORD
```

**Niezmiennik automatu** (utrwalony po sesji 2026-08-23): każde wyjście z
`PROCESSING`/`SYNTHESIZING`/`SPEAKING` **musi** wrócić do `LISTENING_WAKEWORD`. Trzy ścieżki wyjścia
(`speak` → `handle_playback_done`, `end_turn_without_speech`, `reset_to_listening`) są dziś domknięte —
to jest ta część kodu, której refaktoryzacja **nie ma prawa** naruszyć.

### 1.4 Przepływ konfiguracji (CRUD) — źródło potrojenia

```text
  Web UI                REST                       rejestr                  dysk
 ────────              ──────                     ─────────                ──────
 provider_crud   ─>  /llm/providers*     ─>  BackendRegistry   ─>  data/backends/*.json
 _section.js     ─>  /voice/stt/providers* ->  STTRegistry     ─>  data/stt_backends/*.json
 (jeden komponent)->  /voice/tts/providers* ->  TTSRegistry     ─>  data/tts_backends/*.json
                          ▲                          ▲
                          │                          │
                 3 × ten sam router         3 × ten sam rejestr
                 (~100 linii każdy)         (~190 linii każdy)
```

Frontend **ma już** jeden generyczny komponent (`components/provider_crud_section.js`, sparametryzowany
`idPrefix` + nazwami metod). Backend go nie ma — i to jest asymetria warta usunięcia.

---

## 2. Znaleziska

Legenda wagi: **A** = błąd działający na produkcji · **B** = realny koszt rozwoju/ryzyko regresji ·
**C** = czytelność, nawigacja, spójność.

| # | Waga | Znalezisko | Miejsce |
| :-- | :-: | :--- | :--- |
| F1 | **A** | `LLMRouter` serwuje nieświeży preset po edycji aktywnego | `ai/llm/router.py:25-30` |
| F2 | **B** | Cykliczna zależność `ai` ↔ `voice` i `agent` ↔ `ai` (łatana leniwymi importami) | `ai/*/factory.py`, `agent/engine.py:80-89` |
| F3 | **B** | Potrojony rejestr instancji + rozjechane sygnatury `update_instance` | `ai/{llm,stt,tts}/registry.py` |
| F4 | **B** | Potrojony router CRUD dostawców + zduplikowane helpery sekretów | `voice/provider_routes.py`, `network/routes/providers.py` |
| F5 | **B** | `WorldEngine` jako god object — 5 magazynów + budowa promptu w jednej klasie | `world/engine.py` (734) |
| F6 | **B** | Logika domenowa (semantyka upsertu) w warstwie transportu | `world/routes.py:264-290` |
| F7 | **B** | Kodek ramek WS ręcznie powtórzony po obu stronach protokołu | `voice/gateway.py`, `desktop_satellite/protocol_client.py` |
| F8 | **B** | `EventBus` jako worek nietypowanych dictów ze stringowymi kluczami | `agent/engine.py`, `voice/gateway.py` |
| F9 | **C** | Serializacja ramki SSE powtórzona w 3 plikach (5 wariantów) | `routes/chat.py:87`, `routes/sessions.py:102`, `voice/routes.py:171` |
| F10 | **B** | Współdzielone, nietypowane worki stanu przekazywane przez `main.py` | `main.py:110-118`, `voice/gateway.py:277-313` |
| F11 | **B** | `AgentEngine._generate_in_background` — 249 linii, 5 odpowiedzialności | `agent/engine.py:150-398` |
| F12 | **C** | `world/routes.py` — 8 rodzin zasobów w jednym pliku | `world/routes.py` (390) |
| F13 | **C** | Martwy kod: `check_health` (4 implementacje), `get_session_generation_status` | `agent/llm.py:141`, `agent/engine.py:114` |
| F14 | **C** | 18 endpointów bez adnotacji zwrotu; 8 ad-hoc słowników `{"success": ...}` | warstwa REST |
| F15 | **B** | 65 kopii bloku `try/fetch/!ok/catch` + 3 kopie pętli czytnika SSE w JS | `web/js/network/clients/*.js` |
| F16 | **C** | `api_client.js` — 60 metod czystej delegacji | `web/js/network/api_client.js` |
| F17 | **C** | Nazwy plików Web UI nie odpowiadają już nazwom zakładek | `views/extensions*`, `voice_config.js` |
| F18 | **C** | Trzy różne konwencje cyklu życia widoku JS | `views/settings.js:75` vs `extensions.js` vs `home_assistant_view.js` |
| F19 | **C** | Zero narzędzi wymuszających jakość (brak ruff/mypy/eslint), zero testów JS | root `pyproject.toml` |
| F20 | **C** | `chat.js` (726) i `step_rail.js` (782) — widok + transport + czysta logika razem | `web/js/views/chat*` |

---

### F1 · [A] `LLMRouter` serwuje nieświeży preset po edycji aktywnego

`LLMRouter._resolve()` przebudowuje dostawcę **tylko gdy zmieni się `active_id`**:

```python
# ai/llm/router.py:25-30
async def _resolve(self) -> BaseLLMProvider:
    active_id = await self._registry.get_active_backend_id()
    if self._cached_provider is None or active_id != self._cached_active_id:
        ...
```

Docstring uzasadnia to zdaniem „REST nigdy nie edytuje pól istniejącej instancji, tylko
create/switch/delete" (`ai/stt/router.py:7-11` powtarza to samo). **Ta przesłanka przestała być
prawdziwa** wraz z dodaniem `PUT /api/v1/llm/providers/{id}` (`network/routes/providers.py:184`).
Skutek: zmiana modelu, klucza API czy `max_tokens` **aktywnego** presetu zapisuje się na dysk,
UI pokazuje sukces, a agent do restartu serwera używa starej konfiguracji.

`STTRouter`/`TTSRouter` mają to naprawione (klucz cache `(active_id, options)`) **i test regresyjny**
(`test_ai_routers.py::test_stt_router_rebuilds_when_active_instance_options_change_in_place`).
LLM nie ma ani jednego, ani drugiego.

**Potwierdzenie (uruchomione, nie wywnioskowane):**

```text
model przed edycją: llama3
model po edycji   : llama3
AssertionError: STALE: router nadal zwraca 'llama3'   # oczekiwano 'qwen3'
```

**Naprawa:** ujednolicić klucz cache do `(active_id, options)` we wszystkich trzech routerach
(najlepiej jedną wspólną klasą bazową — patrz E2/E3) + test regresyjny wzorowany na STT.

---

### F2 · [B] Cykliczne zależności między `ai` a `voice` i `agent`

Protokoły mieszkają w domenach konsumentów, a konkrety w `ai/` — więc `ai/` musi importować
z powrotem konsumenta:

```text
ai/stt/{factory,providers,registry,router}.py  ──> voice/stt.py   (BaseSTTProvider)
ai/tts/{factory,providers,registry,router}.py  ──> voice/tts.py   (BaseTTSProvider)
voice/provider_routes.py                       ──> ai/stt, ai/tts
ai/llm/*                                       ──> agent/llm.py   (BaseLLMProvider, ToolDefinition…)
agent/engine.py                                ──> ai/llm         (import LENIWY, w ciele funkcji)
```

Kod w `agent/engine.py:80-89` opisuje ten stan wprost:

> „(2) Praktycznie: `server.ai.llm` importuje z powrotem `server.agent.llm`, więc modułowy import
> tworzył cykl, który wywracał się przy każdej kolejności importów zaczynającej się od `server.ai`."

Dwa dodatkowe leniwe importy w `ai/{stt,tts}/registry.py:54,57` (`from server.voice.config import ...`)
utrzymują drugi cykl. Leniwy import to obejście, nie rozwiązanie: przenosi błąd z czasu importu na
czas wykonania i uniemożliwia statyczną weryfikację granicy.

**Naprawa:** wydzielić `server/ports/` — neutralne miejsce na protokoły dzielone przez kernel/pipeline
i adaptery. Szczegóły w sekcji 3.

---

### F3 · [B] Potrojony rejestr instancji + rozjechane sygnatury

`ai/llm/registry.py` (223), `ai/stt/registry.py` (182), `ai/tts/registry.py` (189) to ten sam plik
z podmienionymi nazwami typów: `_ensure_default_instances` / `create_instance` / `update_instance` /
`load_all_instances` / `get_active_backend_id` / `set_active_backend_id` / `delete_instance` /
`get_active_provider` — łącznie z identycznym komentarzem o nierentrantowym `asyncio.Lock`
i identycznym ostrzeżeniem `⚠️` przy fallbacku na pierwszą instancję.

Ten sam wzorzec „katalog plików JSON = kolekcja instancji" występuje jeszcze **trzy razy** poza `ai/`:

* `world/engine.py:150-220` — grupy urządzeń,
* `world/engine.py:226-284` — pokoje (linia w linię ta sama logika co grupy),
* `world/prompts.py` — profile promptu.

**Sześć kopii tego samego magazynu.** Kopiowanie już zaczęło się rozjeżdżać:

```python
# ai/llm/registry.py:112
async def update_instance(self, backend_id: str, name: Optional[str], options: Dict[str, Any])
# ai/stt/registry.py:96  — argumenty w ODWROTNEJ kolejności
async def update_instance(self, backend_id: str, options: Dict[str, Any], name: Optional[str] = None)
```

Oba wywołania są dziś poprawne, ale to pułapka czekająca na copy-paste między plikami, które
z założenia są swoimi lustrami.

**Uwaga o świadomej decyzji:** `docs/manifest.md` (sekcja 3.5) zapisuje, że konsolidacji **nie zrobiono
celowo** — „dopiero gdy wzorzec się ustabilizuje po dodaniu realnego drugiego typu STT/TTS".
Argumentuję, że warunek jest **spełniony inaczej, niż zakładano**: wzorzec ustabilizował się nie przez
drugi typ dostawcy, tylko przez szóstą kopię i pierwszy rozjazd sygnatur. To decyzja do Twojego
zatwierdzenia (D2 w sekcji 5).

---

### F4 · [B] Potrojony router CRUD dostawców

`voice/provider_routes.py` to 270 linii, z czego **linie 76-171 (STT) i 173-268 (TTS) różnią się
wyłącznie trzema literami w nazwach**. Oba bloki są z kolei kopią `network/routes/providers.py`
(schemas / list / set-active / create / update / delete).

Dodatkowo `_mask_secret_options` i `_merge_preserving_secrets` istnieją **dwa razy**
(`provider_routes.py:27-69` ≈ `network/routes/providers.py:16-65`), a trzecia odmiana tej samej idei
to `_mask_token` w `world/routes.py:48`. Reguła „puste pole sekretne = zachowaj obecną wartość" jest
prawdziwie krytyczna (bez niej każdy zapis formularza kasuje klucz API kropkami) — i jest utrzymywana
w trzech miejscach naraz.

**Naprawa:** jedna fabryka `create_provider_crud_router(...)` parametryzowana rejestrem, fabryką
schematów, typem enum i prefiksem ścieżki; helpery sekretów w jednym module. Trzy wywołania zamiast
trzech kopii. Kontrakt REST bez zmian (te same ścieżki, te same DTO).

---

### F5 · [B] `WorldEngine` jako god object

734 linie, **siedem niezależnych odpowiedzialności** w jednej klasie:

| Zakres | Linie | Charakter |
| :--- | :--- | :--- |
| Konfiguracja HA (load/save/test) | 105-144 | magazyn + I/O sieciowe |
| CRUD grup | 150-220 | magazyn plikowy |
| CRUD pokoi | 226-284 | magazyn plikowy (kopia powyższego) |
| Zadeklarowane urządzenia | 290-372 | magazyn + join z katalogiem HA |
| Rejestr nadawców + `_find_speaker_by_room` | 378-433 | magazyn + logika domenowa |
| Delegacje do `PromptSectionStore`/`WorldPromptStore` | 439-493 | **czysta fasada, 14 metod bez własnej logiki** |
| `build()` — implementacja `WorldInterface` | 499-651 | orkiestracja + renderowanie + `dispatch` |

Sam `build()` to 152 linie, w których dzieje się: pobranie profilu nadawcy, łagodna degradacja HA,
renderowanie listy urządzeń, złożenie `TurnFacts`, ewaluacja sekcji, definicje dwóch narzędzi
wpisane inline jako literały (`_GET_TIME_TOOL`, `_SPEAK_IN_ROOM_TOOL`, linie 576-599) oraz
domknięcie `dispatch` z pełną implementacją `speak_in_room` (linie 607-643).

To jest ten plik, w którym „nawigacja staje się uciążliwa" — żeby dodać jedno narzędzie, trzeba
wejść w środek funkcji budującej prompt.

---

### F6 · [B] Logika domenowa w warstwie transportu

`world/routes.py:264-290` (`register_sender`) rozstrzyga **semantykę upsertu**: które pola pominięte
znaczą „zachowaj obecne" (`capabilities`, `display_name`), a gdzie `None` to legalna wartość
(`room_id`). To reguła domenowa — dziś nie da się jej przetestować bez podniesienia HTTP i nie
obowiązuje żadnego innego wywołującego `WorldEngine.register_sender()`.

Ten sam wzorzec (poprawnie!) mieszka po stronie silnika przy tokenie HA: `WorldEngine.save_config`
sam pilnuje „brak tokenu = zachowaj obecny" (`world/engine.py:110-127`), z komentarzem uzasadniającym,
dlaczego to należy do backendu. Dwa różne miejsca dla tej samej zasady.

---

### F7 · [B] Kodek ramek WS powtórzony po obu stronach

`packages/shared/src/shared/voice_protocol.py` deklaruje **nazwy** ramek (dwa enumy + trzy stałe
audio), ale **nie potrafi ich zakodować ani zdekodować**. W efekcie obie niezależne usługi robią to
ręcznie, symetrycznie i osobno:

| Operacja | Serwer | Satelita |
| :--- | :--- | :--- |
| Wysłanie ramki kontrolnej | `gateway.py:96` `json.dumps({"type": ...})` | `protocol_client.py:58` to samo |
| Ramka z payloadem | `gateway.py:104-115` `send_client_config` ręcznie | `session.py:91-92` `frame["silence_duration_ms"]` |
| Odbiór + rozpoznanie typu | `gateway.py:262-274` `json.loads` + `data.get("type")` | `protocol_client.py:72-77` `parse_server_message_type` |
| Handshake | `gateway.py:241-257` ręczne parsowanie `hello.capabilities` | `session.py:71` `send_hello(["mic","speaker"])` |

To **jedyne** miejsce w systemie, gdzie kontrakt między dwiema usługami nie jest typowany Pydantikiem
(REST ma `shared/contracts.py`, wszystkie DTO zwalidowane). `desktop_satellite/session.py:91` sięga
po `frame["silence_duration_ms"]` na surowym dicie — literówka po jednej stronie ujawni się dopiero
jako `KeyError` w runtime u klienta.

To zarazem **jedyny realny przypadek** hipotezy nr 1 z Twojego zlecenia: niskopoziomowe plumbing
protokołu żyje w pliku orkiestracji połączenia.

---

### F8 · [B] `EventBus` jako worek nietypowanych dictów

`Event[T]` jest generyczny, ale w praktyce zawsze używany jako `Event[Any]`, a payload to dict ze
stringowymi kluczami czytanymi w kilkunastu miejscach:

```python
event.payload.get("session_id")        # agent/engine.py × 7
event.payload.get("target_client_id")  # voice/gateway.py × 3
event.payload.get("kind") == "reasoning"
event.payload.get("chunk", "")
payload["state"]                       # voice/gateway.py:88
```

Konsekwencje są realne i już się zmaterializowały: rozdzielenie `session_id` od `target_client_id`
(2026-08-22) było naprawą błędu, w którym zdarzenia lądowały pod tagiem, którego nikt nie słuchał —
klasy błędu, którą typowany payload uniemożliwiłby na etapie edycji.

Dwa dodatkowe fakty o magistrali, warte utrwalenia w dokumentacji (a nie w komentarzach rozsianych
po kodzie):

* `EventBus.publish()` **połyka wyjątki handlerów** (`event_bus.py:67`) — stąd konieczność
  `try/except` w `VoiceSession.speak()`, inaczej błąd TTS ginął bez śladu.
* Handlery wołane są **sekwencyjnie z `await`** — stąd `_start_speaking()` musi odpalać syntezę jako
  zadanie w tle, inaczej TTS blokuje publikację `CHAT_DONE` do kanału SSE Web UI.

Oba to pułapki wbudowane w projekt magistrali, każda odkryta przez realny błąd.

---

### F9 · [C] Serializacja SSE powtórzona w trzech plikach

```python
yield f"data: {json.dumps({**event.payload, 'type': event.type})}\n\n"
```

Ta sama linia w `network/routes/chat.py:87`, `network/routes/sessions.py:102`,
`voice/routes.py:171`, plus warianty `"data: [DONE]\n\n"` i ramka błędu (`chat.py:88-94`).
Po stronie JS lustrzana pętla czytnika (`getReader` + `TextDecoder` + podział po `\n\n`) występuje
trzy razy (`chat_client.js:147,217`, `voice_client.js:73`).

---

### F10 · [B] Współdzielone worki stanu jako parametry

`main.py:110-118` tworzy trzy gołe kolekcje, które następnie wędrują przez sygnatury dwóch fabryk
routerów i konstruktor `VoiceConnection`:

```python
connected_sender_ids: set[str] = set()
sender_states: dict[str, str] = {}
pending_capabilities: dict[str, list[str]] = {}
```

`create_voice_router` ma przez to **9 parametrów**, `create_voice_status_router` — **8**.
Nic nie gwarantuje, że wszyscy trzej mutujący (`voice_endpoint`, `VoiceConnection._publish_voice_event`,
`gateway.finally`) utrzymają te trzy struktury w spójności; dziś robią to trzy niezależne linie kodu
w dwóch plikach. To jeden byt domenowy — „obecność klienta" — rozmazany na trzy prymitywy.

Dodatkowo `voice/routes.py:119-122` porównuje **nazwę klasy jako string**:

```python
and wakeword_detector_class_name != "ThresholdEnergyWakeWordDetector"
... not any(name.startswith("Mock") for name in (stt_name, tts_name))
```

Zmiana nazwy klasy po cichu zepsuje `is_production_ready` — bez błędu, bez testu.

---

### F11 · [B] `AgentEngine._generate_in_background` — 249 linii

Jedna funkcja z pięcioma odpowiedzialnościami i czterema domknięciami (`_publish`, `_next_seq`,
`_flush_reasoning`, `_build_metadata`):

1. utrwalanie w pamięci sesji,
2. publikacja zdarzeń z dwoma identyfikatorami,
3. pętla ReAct,
4. księgowanie kroków i przebiegów rozumowania (`seq`/`text_offset`),
5. trójścieżkowa obsługa końca tury (sukces / anulowanie / błąd + sanityzacja).

Do tego `_subscribe_session_events` (linie 400-467) to **siedem prawie identycznych handlerów**
różniących się wyłącznie nazwą zdarzenia i kształtem payloadu — idealny kandydat na tabelę.

`AgentEngine` trzyma przy okazji rejestr zadań (`_active_tasks`, `_generation_buffers`) i cztery
metody do jego obsługi, z których jedna (`get_session_generation_status`) jest martwa (F13).

---

### F13 · [C] Martwy kod

* **`check_health()`** — metoda **abstrakcyjna** w `BaseLLMProvider` (`agent/llm.py:141`), więc każdy
  nowy dostawca musi ją zaimplementować. Ma 4 implementacje (`ollama.py:154`,
  `openai_compatible.py:196`, `router.py:42` + testowe atrapy) i **zero wywołań produkcyjnych** —
  nie jest wystawiona w żadnym endpointcie. `docs/manifest.md` potwierdza: zielona dioda przy modelu
  została usunięta 2026-08-23 właśnie dlatego, że opierała się na czymś, co nie jest liveness checkiem.
* **`AgentEngine.get_session_generation_status()`** (`engine.py:114-120`) — zero wywołań, także w testach.
* **`voice/config.py::VoiceProvidersConfig`** — używane wyłącznie przez best-effort migrację legacy
  w dwóch rejestrach. Do usunięcia razem z migracją, gdy uznasz okno migracyjne za zamknięte.

---

### F15-F18, F20 · Web UI

**F15 — 65 kopii tego samego bloku.** Każda metoda w czterech klientach domenowych wygląda tak:

```javascript
try {
  const response = await fetch(`${this.baseUrl}/api/v1/...`);
  if (!response.ok) throw new Error(`HTTP Error: ${response.status}`);
  return await response.json();
} catch (error) {
  console.error('[ApiClient] Błąd ...:', error);
  return null;      // albo [], albo {} — zależnie od metody
}
```

Liczba wystąpień `response.ok`: `agent_client.js` 10, `chat_client.js` 9, `voice_client.js` 18,
`world_client.js` 28. Ujednolicona obsługa błędów (kiedy `null`, kiedy `[]`, kiedy rzucamy) jest dziś
decyzją podejmowaną 65 razy z osobna.

**F16 — `api_client.js`: 60 metod w postaci `foo(...args) { return this._x.foo(...args); }`.**
Fasada powstała, żeby konsumenci nie musieli się zmieniać przy podziale na klientów domenowych —
zapłaciła za to plikiem, który rośnie liniowo z każdym nowym endpointem (2 pliki do edycji zamiast 1).

**F17 — nazwy plików nie odpowiadają zakładkom.** Dziś w UI są: Agent / Dostawcy / **Świat** / **Klienci**.
W kodzie: `views/extensions.js` (= Świat), `views/extensions/ha/*` (= panele Świata),
`views/voice_config.js` (= Klienci, 600 linii), `css/views/extensions.css`, `css/views/voice.css`.
Nazwa „extensions" pochodzi z porzuconego modelu wielorozszerzeniowości, a „voice" z zakładki
przemianowanej na „Klienci". Wchodząc w projekt po tygodniu, szukasz pliku pod nazwą, której nie ma.

**F18 — trzy konwencje cyklu życia widoku.** `SettingsView.activateSection` woła
`section.init(apiClient, navCallback)` (`settings.js:75`), ale `ExtensionsView.init(apiClient)`
ignoruje drugi argument, a `HomeAssistantExtensionView` w ogóle nie ma pary `render()/init()` —
używa `mount(element, apiClient, showToast)`. Kontrakt widoku jest dorozumiany i nieegzekwowany.

**F20 — `chat.js` (726) i `step_rail.js` (782).** `ChatView` łączy: renderowanie DOM, pętlę SSE
(`_runWatchLoop`), polling listy sesji, quick-swap presetu LLM i formatowanie wiadomości.
`StepRailRenderer` łączy: czystą logikę (`buildSegments`, `mergeStepPairs`,
`groupConsecutiveStepsForRender`, `splitThinkFromText` — w pełni testowalną, gdyby ją wyjąć)
z szablonami HTML i mechaniką animacji zwijania.

**F19 — brak jakiejkolwiek automatycznej kontroli jakości.** Nie ma `ruff`, `mypy`, `eslint`,
`prettier`, `package.json` ani jednego testu JS. `AGENTS.md` wymaga „ścisłego typowania: pełne
adnotacje typów w sygnaturach" — dziś to wyłącznie dyscyplina autora. Efekty widać: 18 funkcji bez
adnotacji zwrotu (F14) i literalnie błędna adnotacja w `ai/llm/router.py:37`
(`AsyncIterator[str | ToolCallRequest]` — brakuje `ReasoningChunk`, dodanego 2026-08-23).

---

## 3. Docelowa struktura

### 3.1 Zasada porządkująca

**Nie proponuję kanonicznej Clean Architecture z warstwami `domain/application/infrastructure`.**
Ten projekt ma już własną, spójną i uzasadnioną oś podziału (kernel / silnik świata / pipeline
głosowy / adaptery AI), opisaną i obronioną w `docs/manifest.md`. Narzucenie na to drugiej,
importowanej taksonomii dałoby dwa równoległe słowniki na te same byty — czyli dokładnie odwrotność
celu.

Proponuję **jedną zmianę kierunku zależności** (wydzielenie portów) i **jedną zasadę wewnątrz każdego
modułu**: trzy stałe podkatalogi o tej samej nazwie i tym samym znaczeniu wszędzie.

```text
<moduł>/
├── api/        # trasy HTTP/WS + DTO — TYLKO transport, zero reguł domenowych
├── stores/     # trwałość (pliki JSON) — TYLKO odczyt/zapis, zero reguł domenowych
└── *.py        # domena: reguły, automaty, orkiestracja — zero I/O sieciowego i HTTP
```

Test przynależności: *„czy ten kod zmieni się, gdy zamienię HTTP na gRPC?"* → `api/`.
*„czy zmieni się, gdy zamienię JSON na SQLite?"* → `stores/`. *„czy zostanie taki sam w obu
przypadkach?"* → domena.

### 3.2 Drzewo docelowe

```text
packages/shared/src/shared/
├── config.py              # ConfigStore, sanitize_identifier, get_service_root
├── json_repository.py     # NOWY: generyczny magazyn "katalog plików = kolekcja instancji"  [F3]
├── event_bus.py
├── contracts.py           # DTO REST współdzielone
├── voice_protocol.py      # enumy + stałe (bez zmian)
├── voice_frames.py        # NOWY: kodek ramek — encode/decode, modele Pydantic         [F7]
├── sse.py                 # NOWY: format_sse_event() — jedno miejsce                    [F9]
└── logging.py

services/server/src/server/
├── ports/                 # NOWY — protokoły dzielone przez kernel/pipeline i adaptery  [F2]
│   ├── llm.py             #   BaseLLMProvider + ToolDefinition/ToolCallRequest/ToolResult/
│   │                      #   LLMMessage/ReasoningChunk   (przeniesione z agent/llm.py)
│   ├── stt.py             #   BaseSTTProvider             (przeniesione z voice/stt.py)
│   ├── tts.py             #   BaseTTSProvider             (przeniesione z voice/tts.py)
│   └── wakeword.py        #   WakeWordDetector            (przeniesione z voice/wakeword.py)
│
├── agent/                 # KERNEL — bez zmian w granicach, rozbite w środku          [F11]
│   ├── engine.py          #   API publiczne: interact/interact_stream/watch_session/
│   │                      #   start_interaction/cancel  (~150 linii zamiast 603)
│   ├── turn.py            #   NOWY: TurnRunner — pętla ReAct + księgowanie kroków
│   ├── turn_events.py     #   NOWY: typowane payloady zdarzeń + subskrypcja tabelaryczna [F8]
│   ├── tasks.py           #   NOWY: SessionTaskRegistry — _active_tasks + bufory
│   ├── context_provider.py#   WorldInterface + ContextBuild (ZOSTAJE — brak cyklu)
│   ├── context/  memory/  prompts/
│
├── ai/                    # ADAPTERY — zależą wyłącznie od ports/                      [F2]
│   ├── provider_registry.py  # NOWY: wspólna baza rejestru + routera cache             [F3]
│   ├── llm/{providers/,factory,model_catalog,models,registry,router}.py
│   ├── stt/{providers,factory,models,registry,router}.py
│   └── tts/{providers,factory,models,registry,router}.py
│
├── world/                 # SILNIK ŚWIATA                                          [F5][F6][F12]
│   ├── engine.py          #   fasada WorldInterface + delegacje (~200 linii zamiast 734)
│   ├── turn_context.py    #   NOWY: TurnFacts + renderowanie listy urządzeń
│   ├── prompt_sections.py #   (bez zmian — moduł jest dobry)
│   ├── stores/            #   NOWY: config, rooms, groups, declared_devices, senders, prompts
│   ├── tools/             #   NOWY: registry narzędzi — get_time, speak_in_room, home_assistant
│   ├── clients/           #   NOWY: home_assistant.py (dawne client.py)
│   └── api/               #   NOWY: config, rooms, devices, groups, senders,
│                          #        prompt_sections, prompts  (rozbite world/routes.py)
│
├── voice/                 # PIPELINE SATELIT                                      [F7][F10]
│   ├── session.py         #   automat stanu (bez zmian — jest wzorowy)
│   ├── connection.py      #   NOWY: VoiceConnection (wyjęte z gateway.py)
│   ├── presence.py        #   NOWY: ClientPresenceRegistry — jeden byt zamiast 3 worków
│   ├── events.py
│   └── api/               #   ws.py (endpoint), status.py, clients.py, providers.py
│
├── network/               # BRAMKA
│   ├── gateway.py
│   ├── errors.py          #   NOWY: mapowanie wyjątków domenowych na HTTP — raz       [F14]
│   ├── provider_api.py    #   NOWY: create_provider_crud_router() — jedna fabryka      [F4]
│   └── routes/{health,chat,sessions,prompts}.py
│
└── web/js/
    ├── network/
    │   ├── http.js        #   NOWY: request() — jedno miejsce na fetch/błędy          [F15]
    │   ├── sse.js         #   NOWY: pętla czytnika SSE — jedno miejsce                [F15]
    │   ├── api_client.js  #   namespace'y zamiast 60 delegacji                        [F16]
    │   └── clients/{agent,chat,world,voice}_client.js
    ├── views/
    │   ├── base_view.js   #   NOWY: jawny kontrakt render()/init()/destroy()          [F18]
    │   ├── world/         #   dawne extensions* — nazwa zgodna z zakładką             [F17]
    │   ├── clients/       #   dawne voice_config.js (rozbite)                         [F17]
    │   └── chat/          #   chat_view.js + stream_controller.js + segments.js       [F20]
    └── ...
```

### 3.3 Co ta zmiana daje mierzalnie

| Metryka | Dziś | Po |
| :--- | ---: | ---: |
| Kopie magazynu „katalog JSON = kolekcja" | 6 | 1 |
| Kopie routera CRUD dostawców | 3 | 1 |
| Kopie helperów maskowania sekretów | 3 | 1 |
| Kopie serializacji ramki SSE (Python) | 5 | 1 |
| Kopie bloku `try/fetch/catch` (JS) | 65 | 1 |
| Parametry `create_voice_router` | 9 | 4 |
| Największy plik Python | 734 | ~250 |
| Cykle zależności między pakietami | 2 | 0 |
| Miejsc do edycji przy dodaniu endpointu | 2-3 | 1-2 |

### 3.4 Decyzje z manifestu, które plan ŚWIADOMIE zachowuje

Refaktoryzacja **nie rusza** ani jednej z poniższych — są uzasadnione i obronione w
`docs/manifest.md`, sekcja 5:

* Brak generycznej wielorozszerzeniowości (`PluginProvider`/`Gateway`/`NetworkExtension`) — **nie wraca**.
  `world/tools/` z sekcji 3.2 to zwykły słownik nazwa→handler wewnątrz jednego silnika, **nie** protokół
  między wymiennymi rozszerzeniami.
* Home Assistant jako singleton, nie kolekcja połączeń.
* Adresowanie po natywnym `entity_id`, bez warstwy opaque ID.
* `Room` jako byt World, niezależny od HA Areas; brak pojęcia pokoju w kernelu.
* Katalog urządzeń opt-in.
* World jako jedyny autor promptu tury; podział `system_prompt` / `turn_context` wzdłuż zmienności.
* Modalność jako `capabilities` klienta, nie parametr wywołania.
* Brak uwierzytelniania WS (model zaufanej sieci lokalnej).
* VAD po stronie satelity; wake-word w 100% po stronie serwera.
* Zero natywnych kontrolek przeglądarki w UI.

### 3.5 Co jest dobre i czego lepiej nie „poprawiać"

Żeby refaktoryzacja nie zjadła własnego ogona — te fragmenty są wzorcowe i mają zostać takie, jakie są:

* **`voice/session.py`** — czysty automat stanu, zero wiedzy o gnieździe i magistrali, w pełni
  testowalny (18 testów). Wzorzec do naśladowania, nie do zmiany.
* **`world/prompt_sections.py`** — warunki jako czyste funkcje `TurnFacts -> bool` z zamkniętej listy,
  podstawianie przez `str.replace` (nie `str.format` — ludzie wklejają JSON do promptów).
* **`ai/llm/providers/openai_compatible.py`** — cała brzydota SSE i akumulacja fragmentarycznych
  `tool_calls` zamknięta w adapterze; kernel widzi trzy typy zdarzeń i nic więcej.
* **Sanityzacja błędów u źródła** (`agent/engine.py:368-395`) — jedno miejsce chroni trzy ścieżki
  odbiorcze naraz.
* **`sanitize_identifier`** — konsekwentnie stosowane wszędzie, gdzie ID trafia do nazwy pliku.
* **Strumieniowanie TTS z rozróżnieniem błędu przed/po pierwszym fragmencie** — subtelne i poprawne.

---

## 4. Plan migracji

Etapy są **sekwencyjne i atomowe**: każdy kończy się zielonym `pytest -q` (209 testów jako podłoga,
nigdy mniej), własnym commitem i możliwością zatrzymania się na nim na stałe. Żaden etap nie zmienia
kontraktu REST/WS ani zachowania widocznego dla użytkownika — z jednym jawnym wyjątkiem (E1, naprawa
błędu F1).

Legenda rozmiaru: **S** ≤ 3 pliki · **M** 4-10 plików · **L** > 10 plików.

---

### E0 — Siatka bezpieczeństwa (S, ryzyko: zerowe)

Zanim cokolwiek się ruszy — narzędzia, które wykryją, jeśli coś się zepsuje.

1. `ruff` + `mypy` w `[dependency-groups] dev`, konfiguracja w root `pyproject.toml`.
   Start w trybie **raportującym, nie blokującym** (`mypy --ignore-missing-imports`, bez `--strict`),
   żeby nie zamienić E0 w tygodniowy przystanek.
2. Zapisać bazowy raport („N błędów na starcie") — celem kolejnych etapów jest, żeby ta liczba malała.
3. Test charakteryzujący dla `ai/llm/router.py` opisujący **obecne, błędne** zachowanie F1
   (zostanie odwrócony w E1) — dowód, że test faktycznie łapie różnicę.

**Weryfikacja:** `pytest -q` = 209 · `ruff check` przechodzi lub raportuje znaną listę.
**Wynik:** brak zmian w kodzie produkcyjnym.

---

### E1 — Naprawa F1 + porządki w martwym kodzie (S, ryzyko: niskie)

Jedyny etap zmieniający zachowanie — celowo pierwszy, żeby nie mieszać naprawy błędu z przenoszeniem plików.

1. `LLMRouter._resolve()` → klucz cache `(active_id, options)`, dokładnie jak `STTRouter`.
2. Test regresyjny `test_llm_router_rebuilds_when_active_instance_options_change_in_place`
   (lustro istniejącego testu STT).
3. Poprawić adnotację `LLMRouter.generate_stream` → `AsyncIterator[str | ReasoningChunk | ToolCallRequest]`.
4. Usunąć `AgentEngine.get_session_generation_status()` (zero wywołań).
5. Ujednolicić sygnaturę `update_instance(backend_id, name, options)` we wszystkich trzech rejestrach.
6. **Decyzja D3**: usunąć `check_health()` z `BaseLLMProvider` i 3 implementacji — albo zostawić.

**Weryfikacja:** 209 + 1 nowy test · ręcznie: edycja modelu aktywnego presetu w UI → czat od razu
używa nowego modelu (bez restartu).
**Rollback:** pojedynczy `git revert`.

---

### E2 — `server/ports/` — zerwanie cykli (M, ryzyko: niskie, wysoka wartość)

Czysto mechaniczne przeniesienie: **żadna linia logiki się nie zmienia**, zmieniają się wyłącznie
importy.

1. `agent/llm.py` → `ports/llm.py`; `voice/stt.py` → `ports/stt.py`; `voice/tts.py` → `ports/tts.py`;
   `WakeWordDetector` (Protocol) z `voice/wakeword.py` → `ports/wakeword.py` (konkretne detektory
   zostają w `voice/`).
2. Re-eksporty zgodnościowe w starych lokalizacjach na czas jednego etapu (`from server.ports.llm import *`),
   usunięte na końcu E2 po przełączeniu wszystkich importów.
3. Usunąć leniwy import w `agent/engine.py:87` — cykl zniknął, import wraca na poziom modułu.
4. Usunąć leniwe importy `VoiceProvidersConfig` w `ai/{stt,tts}/registry.py` — `voice/config.py`
   przenieść do `ai/legacy_migration.py` (to należy do migracji rejestrów, nie do pipeline'u głosowego).
5. **`WorldInterface` ZOSTAJE w `agent/context_provider.py`** — nie tworzy cyklu (`world` → `agent`
   jest jednokierunkowe), więc decyzja z manifestu obowiązuje dalej.

**Weryfikacja:** 209 zielonych · `grep -rn "from server.voice" services/server/src/server/ai/` = 0 ·
`grep -rn "from server.ai" services/server/src/server/agent/` = 0 (poza `main.py`).
**Ryzyko:** wyłącznie przeoczony import — wychwyci go import serwera przy pierwszym `pytest`.

---

### E3 — Wspólny magazyn instancji (M, ryzyko: średnie) · **wymaga decyzji D2**

1. `shared/json_repository.py` — generyczny `JsonInstanceRepository[TContent, TInstance]`:
   `create` / `load_all` / `update` / `delete` / `ensure_defaults`, z lockiem, `sanitize_identifier`
   i logowaniem błędu pojedynczego pliku (dziś powtórzone 6×).
2. `ai/provider_registry.py` — wspólna baza `ProviderRegistry` (repozytorium + wskaźnik aktywnego +
   `get_active_provider()` z bezpiecznym fallbackiem) i `ProviderRouter` (cache `(active_id, options)`).
3. `BackendRegistry`/`STTRegistry`/`TTSRegistry` → cienkie specjalizacje (~40 linii każda zamiast ~190):
   typ pliku, prefiks ID, katalog, fabryka, domyślne instancje.
4. `LLMRouter`/`STTRouter`/`TTSRouter` → cienkie specjalizacje `ProviderRouter`.
5. `world/engine.py` — grupy i pokoje przechodzą na to samo repozytorium (usuwa ~130 linii bliźniaczych).

**Weryfikacja:** 209 zielonych — `test_ai_routers.py` (12), `test_llm_providers.py` (10),
`test_stt_tts_providers.py` (10), `test_world_engine.py` (22) pokrywają dokładnie ten obszar.
Dodatkowo: ręczne sprawdzenie, że istniejące pliki w `data/` wczytują się bez migracji
(format na dysku **nie zmienia się w ogóle**).
**Ryzyko:** średnie — dotyka trwałości. Mitygacja: format plików bez zmian, backup `data/` przed etapem.

---

### E4 — Jedna fabryka routera CRUD dostawców (M, ryzyko: niskie)

1. `network/provider_api.py`: `create_provider_crud_router(registry, factory, enum_type, path_prefix,
   dto_type, tag)` + `mask_secret_options` / `merge_preserving_secrets` w jednym miejscu.
2. `network/routes/providers.py` → wywołanie fabryki + endpoint `/models` (specyficzny dla LLM).
3. `voice/provider_routes.py` (270 linii) → dwa wywołania fabryki (~30 linii).
4. `world/routes.py::_mask_token` → ta sama funkcja co reszta.

**Weryfikacja:** 209 zielonych · **porównanie schematu OpenAPI przed i po** (`GET /openapi.json`
zrzucony do pliku przed etapem i zdiffowany) — twardy dowód, że kontrakt REST jest identyczny.
**Ryzyko:** niskie; jedyny realny to zmiana kształtu odpowiedzi — łapie ją diff OpenAPI.

---

### E5 — Rozbicie `WorldEngine` (L, ryzyko: średnie)

Najbardziej pracochłonny etap; robiony **po** E3, bo E3 usuwa z niego połowę objętości.

1. `world/stores/` — `config.py`, `rooms.py`, `groups.py`, `declared_devices.py`, `senders.py`
   (na bazie `JsonInstanceRepository` z E3); `prompts.py` i `prompt_sections.py` przenoszą się tu
   bez zmiany treści.
2. `world/turn_context.py` — `TurnFacts` (przeniesione z `prompt_sections.py`), `_render_devices_section`,
   `_format_capabilities`, `_sections_gained_after_redirect`.
3. `world/tools/` — `home_assistant.py` (dawne `tools.py`), `time.py` (`get_time`),
   `speak_in_room.py`; `registry.py` składający `dict[str, ToolHandler]` + definicje narzędzi
   (dziś literały wewnątrz `build()`).
4. `world/clients/home_assistant.py` — dawne `client.py`; przy okazji jeden współdzielony
   `httpx.AsyncClient` zamiast czterech tworzonych per wywołanie.
5. `world/engine.py` — zostaje fasada: `build()` (~50 linii orkiestracji) + delegacje CRUD.
6. Przenieść semantykę upsertu nadawcy z `world/routes.py` do `WorldEngine.register_sender()` (**F6**),
   z testem jednostkowym zamiast dzisiejszego testu przez HTTP.

**Weryfikacja:** 209 zielonych (`test_world_engine.py` 22, `test_prompt_sections.py` 19,
`test_turn_context_split.py` 6, `test_world_senders_api.py` 7 — najlepiej pokryty obszar w projekcie) ·
**dodatkowo test złotego wzorca**: zrzucić `build(sender_id)` → `(system_prompt, turn_context,
[nazwy narzędzi])` do pliku PRZED etapem i porównać PO. Prompt musi wyjść bajt w bajt ten sam.
**Ryzyko:** średnie — to serce zachowania agenta. Mitygacja: test złotego wzorca powyżej.

---

### E6 — Rozbicie `world/routes.py` (S, ryzyko: niskie)

`world/api/{config,rooms,devices,groups,senders,prompt_sections,prompts}.py`, każdy ~50 linii,
składane przez `world/api/__init__.py::create_world_router()`.
Przy okazji: `DeletionResponse` DTO zamiast 8 ad-hoc słowników i adnotacje zwrotu na wszystkich
endpointach (**F14**).

**Weryfikacja:** 209 zielonych + diff OpenAPI (jak w E4).

---

### E7 — Rozbicie `AgentEngine` + typowane zdarzenia (M, ryzyko: średnie)

1. `agent/turn_events.py` — dataclassy payloadów (`ChunkPayload`, `ToolStepPayload`,
   `TurnLifecyclePayload`) z `session_id` i `target_client_id` jako **polami**, nie kluczami stringów;
   `subscribe_session_events()` tabelaryczne zamiast siedmiu handlerów (**F8**).
2. `agent/tasks.py` — `SessionTaskRegistry` (zadania + bufory generacji).
3. `agent/turn.py` — `TurnRunner`: pętla ReAct, księgowanie `seq`/`text_offset`, trzy ścieżki końca tury.
4. `agent/engine.py` — publiczne API delegujące do powyższych.
5. `voice/gateway.py` i `network/routes/*` czytają typowane payloady zamiast `.get("...")`.

**Weryfikacja:** 209 zielonych (`test_chat_api.py` 12, `test_reasoning_split.py` 6,
`test_voice_turn_delivery.py` 4, `test_client_registration_gate.py` 5) ·
ręcznie: tura z narzędziem + rozumowaniem renderuje się w Web UI w poprawnej kolejności
(to jest dokładnie ten obszar, w którym `text_offset`/`seq` już raz odwróciły kolejność).
**Ryzyko:** średnie — `metadata.steps`/`metadata.reasoning` **musi** zachować dzisiejszy kształt JSON,
bo w `data/sessions/*.json` leżą realne dane użytkownika, których się nie migruje (decyzja z manifestu).

---

### E8 — `voice/`: obecność klienta + kodek protokołu (M, ryzyko: średnie)

1. `shared/voice_frames.py` — modele Pydantic ramek + `encode_frame()` / `decode_frame()`.
   Serwer i satelita przestają robić `json.dumps`/`json.loads` na piechotę (**F7**).
   `desktop_satellite/protocol_client.py` i `session.py` przechodzą z `dict` na typowane ramki.
2. `voice/presence.py` — `ClientPresenceRegistry` zamiast trzech worków (`connected_sender_ids`,
   `sender_states`, `pending_capabilities`) (**F10**). `create_voice_router` schodzi z 9 do 4 parametrów.
3. `voice/connection.py` — `VoiceConnection` wyjęte z `gateway.py`; `voice/api/ws.py` — sam endpoint.
4. `voice/api/{status,clients,providers}.py` — rozbite `routes.py` + `provider_routes.py`;
   DTO z `routes.py` przenoszą się do `voice/api/dto.py` (dziś są trzy różne miejsca na DTO).
5. `is_production_ready` przestaje porównywać nazwy klas — właściwość `is_placeholder` na protokołach
   (**F10**, koniec ze stringly-typed).

**Weryfikacja:** 209 zielonych (`test_voice_pipeline.py` 18, `test_session.py` 11 po stronie satelity,
`test_voice_clients_dashboard.py`, `test_voice_connected_senders.py`) ·
**ręcznie, obowiązkowo**: pełna tura na żywo z `desktop_satellite` — wake-word → nagranie → odpowiedź
głosowa → powrót do nasłuchu, plus `voice_satellite_sim.py`.
**Ryzyko:** średnie — zmiana dotyka kontraktu między dwiema usługami. Format ramek na drucie
**nie zmienia się** (te same klucze JSON), więc stary klient i nowy serwer pozostają zgodne.

---

### E9 — Web UI (L, ryzyko: niskie technicznie, wysokie „hałasowo")

1. `network/http.js` — jeden `request()` z jednolitą polityką błędów; 4 klienty domenowe chudną
   o ~60% (**F15**).
2. `network/sse.js` — jedna pętla czytnika; trzy kopie znikają.
3. `api_client.js` → namespace'y (`apiClient.world.getRooms()`), stara płaska fasada zostaje
   przez jeden etap jako `@deprecated`, potem znika wraz z mechaniczną zamianą wywołań (**F16**).
4. Zmiana nazw na zgodne z zakładkami: `views/extensions*` → `views/world/`,
   `voice_config.js` → `views/clients/` (rozbite na `config_panel` / `clients_list` / `live_status`),
   analogicznie CSS (**F17**).
5. `views/base_view.js` — jawny kontrakt `render()/init(ctx)/destroy()`; `HomeAssistantExtensionView`
   przechodzi z `mount()` na ten sam kontrakt (**F18**).
6. `chat.js` → `chat_view.js` + `stream_controller.js`; `step_rail.js` → `segments.js` (czysta logika)
   + `step_rail_renderer.js` (DOM) (**F20**).
7. **Decyzja D4**: `package.json` + `vitest` i pierwsze testy jednostkowe dla `segments.js`
   (`buildSegments`/`mergeStepPairs`/`splitThinkFromText` to czyste funkcje o realnej złożoności —
   dziś jedyna nietestowana logika o tym ciężarze w projekcie).

**Weryfikacja:** brak testów automatycznych po tej stronie (patrz D4) → **checklista ręczna**
w przeglądarce: czat (streaming, rozumowanie, kroki narzędzi, historia po odświeżeniu), Dashboard,
Ustawienia × 4 zakładki, CRUD każdego zasobu, dashboard Klientów na żywo (connect/disconnect/wake-word),
konsola bez błędów.
**Ryzyko:** niskie technicznie, ale to najwięcej dotkniętych plików — dlatego na końcu.

---

### E10 — Dokumentacja i domknięcie (S)

1. `docs/manifest.md`: nowe drzewo katalogów (dziś nie wymienia `ai/`, `world/prompt_sections.py`
   ani połowy `voice/`), sekcja o `ports/`, aktualizacja decyzji zrewidowanych przez D1-D3.
2. `docs/onboarding.md`: poprawić trzy nieaktualne miejsca wykryte przy audycie —
   punkt 4 „Zaplanowane" (opisuje nieistniejący podział zakładek Kernel/Świat/Głos i `kernel_config.js`),
   sekcja o uruchamianiu satelity (twierdzi, że STT/TTS to Mock i odsyła do zakładki „Głos").
3. Usunąć `REFACTORING_PLAN.md`, przeniósłszy trwałą treść do obu dokumentów.
4. Zaktualizować pamięć projektu.

---

### 4.1 Podsumowanie etapów

| Etap | Zakres | Rozmiar | Ryzyko | Usuwa | Zależy od |
| :-- | :--- | :-: | :-: | :--- | :--- |
| E0 | Narzędzia jakości | S | — | F19 (częściowo) | — |
| E1 | Naprawa F1 + martwy kod | S | niskie | F1, F13, F3 (część) | E0 |
| E2 | `ports/` — zerwanie cykli | M | niskie | F2 | E1 |
| E3 | Wspólny magazyn instancji | M | średnie | F3 | E2 |
| E4 | Jedna fabryka CRUD dostawców | M | niskie | F4 | E3 |
| E5 | Rozbicie `WorldEngine` | L | średnie | F5, F6 | E3 |
| E6 | Rozbicie `world/routes.py` | S | niskie | F12, F14 | E5 |
| E7 | Rozbicie `AgentEngine` | M | średnie | F8, F11 | E2 |
| E8 | `voice/`: obecność + kodek ramek | M | średnie | F7, F10 | E7 |
| E9 | Web UI | L | niskie | F15-F18, F20 | E4, E6, E8 |
| E10 | Dokumentacja | S | — | dług dokumentacyjny | wszystkie |

**Ścieżka minimalna** (gdybyś chciał zatrzymać się wcześnie): **E0 → E1 → E2 → E3 → E4** usuwa błąd
produkcyjny, oba cykle i największą duplikację przy umiarkowanym nakładzie — i już samo to zdejmuje
większość dzisiejszej „uciążliwości nawigacyjnej" przy zmianach w konfiguracji dostawców.

---

## 5. Decyzje do Twojego zatwierdzenia

Cztery miejsca, w których plan rewiduje coś świadomie zapisanego albo wykracza poza czystą
refaktoryzację. Nie ruszam ich bez Twojej zgody.

**D1 — Przeniesienie protokołów do `server/ports/` (E2).**
`docs/manifest.md` zapisuje, że `BaseLLMProvider` „zostaje w `agent/` (kernel jest jego właścicielem,
tak jak `WorldInterface`)". Argument za rewizją: ta własność **już się nie utrzymała** — dwa cykle
importów łatane leniwymi importami są tego dowodem. `WorldInterface` w tym planie **zostaje w `agent/`**,
bo tam żaden cykl nie powstał — czyli decyzja obowiązuje dokładnie tam, gdzie się broni.
→ *Zgoda / zostawiamy protokoły na miejscu i żyjemy z leniwymi importami?*

**D2 — Konsolidacja rejestrów (E3).**
Manifest odracza ją wprost do momentu „aż wzorzec się ustabilizuje po dodaniu realnego drugiego typu
STT/TTS". Argument za rewizją: wzorzec ustabilizował się inaczej — mamy sześć kopii i pierwszy rozjazd
sygnatur (F3), a drugi typ STT/TTS nadal nie istnieje.
→ *Zgoda / czekamy dalej na drugi realny backend STT?*

**D3 — Usunięcie `check_health()` (E1).**
Cztery implementacje, zero wywołań; dla dostawców OpenAI-compatible sprawdza tylko, czy klucz API jest
niepusty — więc jako liveness check i tak byłby mylący. Alternatywa: zostawić i wystawić jako
`GET /api/v1/llm/providers/{id}/health` z uczciwą semantyką.
→ *Usunąć / wystawić / zostawić martwe?*

**D4 — Testy JS + `package.json` (E9).**
7 046 linii JS bez jednego testu, w tym `segments.js` z realną logiką parsowania i scalania kroków.
Koszt: nowa zależność narzędziowa (Node/vitest) w projekcie, który dziś jest czysto pythonowy —
świadomie prosty w uruchomieniu.
→ *Dodajemy vitest / zostajemy przy weryfikacji ręcznej w przeglądarce?*

---

## 6. Zasady obowiązujące w każdym etapie

1. **Zero regresji** — `python -m uv run python -m pytest -q` musi dawać ≥ 209 zielonych po każdym
   etapie. Spadek liczby testów bez jawnego uzasadnienia = błąd, nie uproszczenie.
2. **Kontrakt na zewnątrz się nie zmienia** — ścieżki REST, kształty DTO, ramki WS i format plików
   w `data/` zostają bajt w bajt takie same (poza E1, gdzie zmiana zachowania jest celem).
   Narzędzie kontroli: diff `openapi.json` przed/po.
3. **Jeden etap = jeden commit** z opisem w konwencji projektu (`refactor(zakres): ...`).
4. **Przenoszenie ≠ przepisywanie.** W etapach mechanicznych (E2, E6, E8-część) treść funkcji
   przenosi się bez zmian — inaczej nie da się odróżnić skutku przeprowadzki od skutku poprawki.
5. **Komentarze „dlaczego" jadą razem z kodem.** W tym repo komentarze niosą historię realnych błędów
   (dlaczego `stop()` a nie `abort()`, dlaczego synteza poza handlerem, dlaczego offset a nie tylko `seq`).
   Zgubienie ich w przeprowadzce kosztowałoby więcej niż sama refaktoryzacja zyskuje.
6. **`data/` przed E3 i E5** — kopia zapasowa katalogu przed etapami dotykającymi trwałości.
