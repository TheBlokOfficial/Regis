# Regis: Manifest Projektu

Ten dokument definiuje duszę projektu Regis. Służy jako najwyższy kompas dla programistów oraz agentów AI pracujących przy kodzie. Jeśli jakakolwiek nowa funkcja, narzędzie lub decyzja architektoniczna jest sprzeczna z tym dokumentem — należy ją odrzucić.

---

## 1. Czym jest Regis?

Projekt to **lekka i błyskawiczna warstwa abstrakcji** pomiędzy domownikami a urządzeniami Smart Home.
Jego siłą napędową nie jest paląca potrzeba, lecz czysta, technologiczna pasja (hobby). Celem samym w sobie jest zbudowanie **autonomicznej, modularnej i perfekcyjnie zorganizowanej architektury** zarządzania domem. Z tego powodu jakość, spójność i czystość kodu są tu ważniejsze niż szybkie dostarczanie funkcji (tzw. "dowożenie").

---

## 2. Złota Zasada: Przezroczystość (Zasada "Nie Przeszkadzaj")

**System musi być organiczny i nigdy nie może wchodzić użytkownikowi w drogę.**

Największym grzechem w tym projekcie jest implementacja funkcji "na siłę", tylko dlatego, że technologia na to pozwala. Jeśli nowa funkcjonalność (nawet najbardziej zaawansowana technologicznie) sprawia, że system staje się uciążliwy, wolny lub irytujący — należy ją usunąć lub całkowicie przeprojektować. W najgorszym scenariuszu Regis ma być po prostu **niewidzialny i bezkolizyjny** dla domowników.

---

## 3. Architektura (Stan Obecny)

Poniższy opis odnosi się do **aktualnej konfiguracji** systemu. Architektura docelowa opisana jest w §3.6 — jest zbliżona do obecnej, z tym że Windows Node pełni rolę opcjonalnego, lokalnego providera zamiast wymaganego węzła produkcyjnego.

### 3.1 Kontroler (`controller`)
- **Rola:** Mózg systemu i jedyne źródło prawdy. Zarządza rejestrem aktywnych węzłów roboczych, routingiem sesji oraz wykonywaniem narzędzi Home Assistant.
- **Deployment:** Zawsze i tylko Raspberry Pi 5 (Linux). Singleton — może istnieć dokładnie jedna instancja. Dystrybuowany jako pakiet `.whl`.
- **Kluczowa zasada:** Kontroler to lekki daemon — nigdy nie hostuje modelu LLM. Jest jedynym punktem komunikacji z Home Assistant; węzły robocze nigdy nie mają dostępu do HA bezpośrednio.
- **Routing:** Kontroler wybiera najlepszy dostępny węzeł (preferuje wyższy tier) dla każdej nowej sesji. Graceful migration między aktywnymi sesjami nie jest zaimplementowana — system działa na zasadzie best-effort.

### 3.2 Węzeł roboczy (`worker`) — Linux / RPi5
- **Rola:** Zawsze uruchomiony na RPi5 komponent bezpieczeństwa systemu. Hostuje dwa serwisy offline:
  1. **Parser offline** — lekki model zdolny do pracy na RPi5, z Structured Outputs. Obsługuje proste komendy urządzeń gdy żaden pełny provider LLM nie jest dostępny.
  2. **Awaryjny STT** — lekki model Whisper do transkrypcji audio w trybie offline.
- **Deployment:** Pakiet `.whl` instalowany przez `pip` na RPi5 (Linux). Brak UI — czysty serwer HTTP.
- **Uwaga:** RPi5 nie ma podłączonego mikrofonu — **nie nagrywa dźwięku samodzielnie**. STT działa wyłącznie na danych strumieniowanych przez Satelity.
- **Status:** Parser i awaryjny STT są ostatnią linią obrony — aktywowane gdy system przechodzi w tryb fallback (brak przynajmniej jednego providera spośród STT, LLM, TTS). Nie są częścią normalnej ścieżki produkcyjnej.

### 3.3 Węzeł (`node`) — Windows PC
- **Rola:** Pełnoprawna **aplikacja Windows** z interfejsem terminalowym. Łączy trzy warstwy w jedną całość: UI (dashboard, monitor konwersacji), Worker LLM (inferencja lokalna) i Satellite (przechwytywanie audio). Nie jest to wyłącznie "usługa w tle" — terminal UI jest pierwszorzędnym elementem. Ikona w pasku zadań to jedynie mechanizm życia procesu.
- **Deployment:** Dystrybuowany jako **Windows Installer** (`RegisNodeSetup.exe`, Inno Setup) — wymaga Python zainstalowanego w systemie.
- **Rola producencyjna:** Opcjonalna. W typowej produkcji Windows Node nie jest uruchomiony — system korzysta z providerów chmurowych. Gdy jest aktywny, automatycznie rejestruje się jako lokalny provider STT, LLM i TTS.
- **Główne zastosowania:** Środowisko deweloperskie (lokalny LLM, tańszy STT/TTS), awaryjny fallback gdy chmura jest niedostępna.
- **Koegzystencja:** Worker (inferencja LLM) i Satellite (przechwytywanie audio) mogą działać jednocześnie — nie wykluczają się.

### 3.4 Satelita — typy interfejsów
Każdy interfejs użytkownika jest architektonicznie Satelitą — różnią się medium:
  - **ESP32** — miniaturowy, dedykowany sprzęt w domu; robi VAD i strumieniowanie audio. Tani, niskoprądowy, idealny do stałego montażu.
  - **Windows PC** (`node`) — aplikacja z UI terminalowym; robi VAD + WakeWord lokalnie, resztę deleguje do centrum.
  - **Linux** — wariant headless lub terminalowy.

### 3.4 Pipeline Przetwarzania Audio (Rozstrzygnięte)

Każde żądanie głosowe przechodzi przez następujące etapy — podział pracy między Satelitą a Węzłem Roboczym zależy od możliwości sprzętu:

**Dla ESP32 (ograniczony sprzęt):**
```
[ESP32]                              [Worker Node]
Cisza
 → VAD wykrywa mowę ludką
 → strumieniuje audio ──────────────→ WakeWord detection
                                          → brak WakeWord → odrzuć
                                          → WakeWord! → STT (Whisper)
                                          → LLM (pętla ReAct + narzędzia)
                                          → TTS
                       ←────────────── odpowiedź audio
 → odgrywa odpowiedź
```

**Dla Desktop PC (pełny sprzęt):**
```
[Desktop Satelita]                   [Worker Node]
Cisza
 → VAD wykrywa mowę
 → WakeWord detection (lokalnie)
 → przesyła audio ──────────────────→ STT (Whisper) — standaryzacja jakości
                                       → LLM (pętla ReAct + narzędzia)
                                       → TTS
                   ←───────────────── odpowiedź audio
 → odgrywa odpowiedź
```

**Kluczowe decyzje projektowe:**
- **VAD (Voice Activity Detection)** siedzi zawsze na Satelicie — jest to lekki algorytm energetyczny (kilka KB), radykalnie redukuje niepotrzebne strumieniowanie.
- **WakeWord** na ESP32 jest zbyt kosztowny — siedzi na Węźle Roboczym. Na desktopie może siedzieć lokalnie.
- **STT zawsze na Węźle Roboczym** — standaryzuje jakość transkrypcji niezależnie od Satelity. Jeden model Whisper = jedna jakość dla wszystkich urządzeń.

---

## 3.5 Warstwa Integracji (Rozstrzygnięta Zasada Architektoniczna)

**Home Assistant jest jedną z możliwych integracji — nie jedyną.**

Katalog `integrations/` to granica między logiką systemu a światem zewnętrznym. HA jest pierwszą i prawdopodobnie największą integracją (żarówki, przełączniki, klimatyzacja, odtwarzacze — wszystko co najłatwiej podłączyć przez HA), ale architektura nie zakłada jego wyłączności.

Przyszłe integracje mogą obejmować m.in.:
- Bezpośrednia komunikacja MQTT
- Inne platformy Smart Home (np. Zigbee2MQTT)
- Własne skrypty i usługi sieciowe
- Dowolny inny endpoint, który ma sens w kontekście sterowania domem

**Konsekwencja dla kodu:** `ToolsRegistry` i `RemoteToolsRegistry` są agnostyczne wobec źródła narzędzi — rozmawiają z `integrations/` przez abstrakcyjny interfejs, nie bezpośrednio z HA. Dodanie nowej integracji oznacza: nowy plik w `integrations/`, nowe narzędzie w `protocol/schemas.py` i nowy handler w `protocol/tools_registry.py`. Żadne inne warstwy nie wymagają zmian.

---

## 3.6 Wizja Docelowa

Cel projektu: **RPi5 jako lekkie, stałe centrum** z chmurą jako domyślnym dostawcą mocy obliczeniowej. Zakup dedykowanego sprzętu (mini PC) nie jest wymagany — architektura skaluje się przez wymianę providerów, nie przez kupowanie sprzętu.

```
┌──────────────────────────────────────────┐
│           CENTRUM (RPi5, 24/7)           │
│                                          │
│  [Controller]  ←──→  [Parser offline]      │
│   routing              offline fallback  │
│   rejestr              STT awaryjny      │
│   proxy HA                               │
└──────────────────────────────────────────┘
          ↑              ↑            ↑
       [ESP32]       [Windows]     [Linux]
    VAD+stream     VAD+WW+UI      terminal
               Satelity — cienkie klienty
                         ↕
         ┌───────────────────────────────┐
         │     PROVIDERY (dynamiczne)    │
         │                               │
         │  LLM:  OpenRouter / Ollama    │
         │  STT:  Cloud API / Whisper    │
         │  TTS:  Cloud API / Piper      │
         └───────────────────────────────┘
```

**Kluczowe właściwości docelowego układu:**
- RPi5 jest zawsze włączony. Hostuje tylko Controller i Parser — nic ciężkiego obliczeniowo.
- Chmura (OpenRouter + cloud STT/TTS) jest domyślnym providerem — bez zakupu dodatkowego sprzętu.
- Windows Node rejestruje się jako lokalny provider gdy uruchomiony (dev, emergency). System automatycznie z niego korzysta.
- Gdy chmura podrożeje lub pojawi się sensowny sprzęt lokalny — podmiana providera nie wymaga zmian w architekturze.

---

## 4. Rejestr Encji (Entity Registry)

Kontroler jest jedynym źródłem prawdy. Wszystkie procesy w systemie — Satelity i Węzły Robocze — **rejestrują się** w Kontrolerze przy starcie oraz cyklicznie odnawiają swą rejestrację w tle (Continuous Registration). Dostarczają mu w ten sposób metadanych o sobie, a dzięki pętli ponawiania uodpornione są na restarty Kontrolera. Kontroler używa tych metadanych do podejmowania decyzji routingowych i budowania kontekstu dla modelu.

### Metadane Satelity
Każda Satelita przy rejestracji podaje:
- `id` — unikalny identyfikator urządzenia
- `room` — pomieszczenie, w którym fizycznie się znajduje (np. `"salon"`, `"sypialnia"`)
- `type` — typ Satelity (`esp32`, `desktop`, `terminal`)
- `capabilities` — co potrafi robić (`audio_in`, `audio_out`, `text`)
- `wakeword_local` — czy obsługuje WakeWord lokalnie (prawda dla desktopów, fałsz dla ESP32)

### Metadane Węzła Roboczego
Każdy Węzeł Roboczy przy rejestracji podaje:
- `id` — unikalny identyfikator
- `host` / `port` — adres sieciowy węzła
- `model_name` — konkretny model Ollamy (np. `qwen3.5:9b`)
- `tier` — klasa modelu (`butler` lub `regis`)

### Kontekst Przestrzenny (Spatial Context Filtering)

To jest kluczowy mechanizm umożliwiający efektywną pracę małych modeli.

Gdy Satelita z pomieszczenia `salon` wysyła żądanie, Kontroler **nie podaje modelowi pełnej listy urządzeń domowych**. Zamiast tego filtruje ją do urządzeń przypisanych do pokoju `salon` i buduje dla modelu wąski, precyzyjny kontekst. Lekki parser operuje wtedy na liście 5 urządzeń zamiast 50 — to nie jest ograniczenie, to jest precyzja.

**Otwarta kwestia — cross-room commands:** Co gdy użytkownik w salonie mówi "wyłącz światło w sypialni"? Propozycja: model dostaje domyślnie swój pokój, ale posiada narzędzie `get_devices(room=...)` pozwalające mu sięgnąć po inne pomieszczenie gdy wyraźnie o to prosi. Większy model na desktopie może od razu otrzymywać pełną listę urządzeń. **Nierozstrzygnięte — wymaga dalszej dyskusji.**

### Co Kontroler synchronizuje do Węzłów
Kontroler przechowuje i dystrybuuje:
- **Prompty systemowe** — tożsamość Regisa, instrukcje behawioralne (rdzeń persony)
- **Historia konwersacji** — aktywne sesje, umożliwia migrację kontekstu między węzłami
- **Rejestr wszystkich encji** — lista aktywnych Satelit i Węzłów z metadanymi

---

## 5. System Providerów i Degradacja

System działa w oparciu o **rejestr providerów** dla trzech krytycznych komponentów. Provider to dowolny serwis zdolny obsłużyć dany komponent — niezależnie od tego czy jest lokalny czy chmurowy. Dla Kontrolera nie ma znaczenia skąd pochodzi provider — tylko czy jest dostępny i zarejestrowany.

| Komponent | Przykładowi providerzy | Priorytet między providerami |
|---|---|---|
| **STT** | Cloud Whisper API, lokalny Faster-Whisper (Windows) | Lokalny > Cloud (koszt) |
| **LLM** | OpenRouter cloud, Ollama lokalnie (Windows) | Cloud > Lokalny (jakość) |
| **TTS** | Cloud TTS API, lokalny Piper/XTTS (Windows) | Lokalny > Cloud (koszt) |

### Dwustanowa degradacja

System zna tylko dwa stany operacyjne:

**Tryb pełny** — każdy komponent ma przynajmniej jednego dostępnego providera:
```
STT: [≥1 provider] AND LLM: [≥1 provider] AND TTS: [≥1 provider]
→ pełny agent ReAct, pełna rozmowa głosowa z TTS
```

**Tryb fallback** — brakuje providera dla choćby jednego komponentu:
```
STT: [0] LUB LLM: [0] LUB TTS: [0]
→ Parser offline (RPi5, lekki model), tylko proste komendy urządzeń, brak TTS
```

Przejście na fallback jest atomowe — system nie operuje w stanach częściowych. Użytkownik zawsze wie w jakim trybie jest system i czego może oczekiwać.

**Uwaga architektoniczna:** Parser (RPi5) jest osobnym, zawsze dostępnym mechanizmem bezpieczeństwa — nie jest częścią systemu providerów i nie wymaga rejestracji.

---

## 6. Persona Regisa

**Zasada: Dla użytkownika zawsze istnieje jeden Regis.** Niezależnie od tego, który model pracuje pod spodem, persona i zachowanie muszą być spójne.

### Charakter
Regis jest **charakterny, rzeczowy i bezpośredni.** Nie owija w bawełnę. Priorytetem jest szybkość, niezawodność i precyzja. Nie jest chatbotem — jest narzędziem z osobowością. Mówi do rzeczy, nie dopełnia odpowiedzi niepotrzebnymi wstępami ani podziękowaniami.

### Implementacja spójności między trybami
- **Wspólny rdzeń persony:** W każdym prompcie, niezależnie od trybu i tieru, osadzony jest nienaruszalny opis tożsamości Regisa. Jego ton i styl nie zmieniają się — Baseline brzmi tak samo jak Agent.
- **Graceful Degradation (Elegancki Upadek):** Baseline nigdy nie udaje, że potrafi coś, czego nie potrafi. Odpowiada zwięźle i bez przepraszania. Brak tłumaczeń technicznych.
- **Capability Layer (Warstwa Możliwości):** Prompty pisane są warstwowo. Rdzeń persony jest stały. Zestaw narzędzi i tryb pracy (NLU vs ReAct) zmienia się w zależności od tieru aktywnego węzła.

---

## 7. Aktualny Dług Architektoniczny

**Zrealizowano (historycznie):**
- Rozbicie monolitu na trzy niezależne usługi (`controller`, `controller.worker`, `node`)
- Izolacja konfiguracji na profile per instancja (pliki `.env`)
- Auto-Discovery węzłów (UDP Broadcast Zero-Conf, `protocol/discovery.py`)
- Rejestr Encji (Satelity i Węzły rejestrują się w Kontrolerze)
- **Izolacja usług (monorepo):** `src/protocol/` oczyszczony do roli chudego kontraktu sieciowego. Każda usługa (`controller`, `node`, `worker`) ma własne kopie `config.py`, `logger.py`, `exceptions.py`, `history_utils.py`, `llm_backends/`. Zero cross-importów między usługami.
- **Warstwa abstrakcji LLM (`llm_backends/`)** w Kontrolerze zaimplementowana (`controller/llm_backends/`). OpenRouter i Ollama jako oddzielne backendy z wspólnym interfejsem `LLMBackend`.

**Aktualny dług (oczekuje realizacji):**
- **Dystrybucja Windows:** Inno Setup (`RegisNodeSetup.exe`) jest zaprojektowany (`docs/distribution_rfc.md`) ale instalator nie jest jeszcze zbudowany produkcyjnie — patrz `TASKS.md`.
- **Pamięć Długoterminowa:** Stary system Notatnika wycięty. Nowe rozwiązanie (np. wektorowe) nie zostało jeszcze zaprojektowane — patrz `TASKS.md`.
- **System Providerów (STT/TTS):** Warstwa abstrakcji dla STT i TTS nie jest jeszcze zaimplementowana. Aktualny kod wymaga Windows Node do lokalnej obsługi audio. Implementacja cloud STT/TTS bez Windows Node wymaga osobnej sesji — patrz `TASKS.md` (`[ARCH — Phase 2]`).
