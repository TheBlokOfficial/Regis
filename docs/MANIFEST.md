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

Poniższy opis odnosi się do **aktualnej, przejściowej konfiguracji** deweloperskiej i testowej. Docelowa architektura opisana jest w §3.6. Obecny układ wynika z ograniczeń sprzętowych RPi5 — nie jest to finalna wizja projektu.

### 3.1 Kontroler (`controller`)
- **Rola:** Mózg systemu i jedyne źródło prawdy. Zarządza rejestrem aktywnych węzłów roboczych, routingiem sesji oraz wykonywaniem narzędzi Home Assistant.
- **Deployment:** Zawsze i tylko Raspberry Pi 5 (Linux). Singleton — może istnieć dokładnie jedna instancja. Dystrybuowany jako pakiet `.whl`.
- **Kluczowa zasada:** Kontroler to lekki daemon — nigdy nie hostuje modelu LLM. Jest jedynym punktem komunikacji z Home Assistant; węzły robocze nigdy nie mają dostępu do HA bezpośrednio.
- **Routing:** Kontroler wybiera najlepszy dostępny węzeł (preferuje wyższy tier) dla każdej nowej sesji. Graceful migration między aktywnymi sesjami nie jest zaimplementowana — system działa na zasadzie best-effort.

### 3.2 Węzeł roboczy (`controller.worker`) — Linux / RPi5 *(komponent przejściowy)*
- **Rola:** Lekki, headless worker LLM uruchamiany na Raspberry Pi 5 jako usługa systemd. Fallback gdy żaden węzeł Windows nie jest dostępny. Obsługuje inferencję tekstową (model 1.5B butler) oraz przetwarzanie audio — przyjmuje surowe pakiety dźwiękowe nadesłane przez Satelity (np. ESP32) i transkrybuje je przez STTEngine.
- **Deployment:** Pakiet `.whl` instalowany przez `pip` na RPi5 (Linux). Brak UI — czysty serwer HTTP.
- **Uwaga:** RPi5 nie ma podłączonego mikrofonu — **nie nagrywa dźwięku samodzielnie**. STT działa wyłącznie na danych strumieniowanych przez Satelity.
- **Status:** Komponent przejściowy. W docelowej architekturze (§3.6) Worker przenosi się na mini PC, a rola RPi5 jako oddzielnego urządzenia odpada.

### 3.3 Węzeł (`node`) — Windows PC
- **Rola:** Pełnoprawna **aplikacja Windows** z interfejsem terminalowym. Łączy trzy warstwy w jedną całość: UI (dashboard, monitor konwersacji), Worker LLM (inferencja 9B) i Satellite (przechwytywanie audio). Nie jest to wyłącznie "usługa w tle" — terminal UI jest pierwszorzędnym elementem. Ikona w pasku zadań to jedynie mechanizm życia procesu.
- **Deployment:** Dystrybuowany jako **Windows Installer** (`RegisNodeSetup.exe`, Inno Setup) — wymaga Python zainstalowanego w systemie.
- **Koegzystencja:** Worker (inferencja LLM) i Satellite (przechwytywanie audio) mogą działać jednocześnie — nie wykluczają się.
- **Status przejściowy:** W docelowej architekturze (§3.6) Worker odpada z `node` — Windows staje się czystą Satelitą z UI, a inferencja przenosi się na dedykowane centrum.

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

**Konsekwencja dla kodu:** `ToolsRegistry` i `RemoteToolsRegistry` są agnostyczne wobec źródła narzędzi — rozmawiają z `integrations/` przez abstrakcyjny interfejs, nie bezpośrednio z HA. Dodanie nowej integracji oznacza: nowy plik w `integrations/`, nowe narzędzie w `core/schemas.py` i nowy handler w `core/tools_registry.py`. Żadne inne warstwy nie wymagają zmian.

---

## 3.6 Wizja Docelowa

Cel projektu: **pełna centralizacja na jednym dedykowanym urządzeniu** (np. mini PC klasy Minisforum UM760, Ryzen 5 / 16 GB RAM), które zastępuje obecny układ RPi5 + Windows.

```
┌──────────────────────────────────────────┐
│              CENTRUM (Mini PC)           │
│                                          │
│  [Controller]  ←──→  [Worker]            │
│   routing              LLM 9B+           │
│   rejestr              STT (Whisper)     │
│   proxy HA             TTS               │
│                                          │
│  [Home Assistant / inne integracje]      │
└──────────────────────────────────────────┘
         ↑              ↑            ↑
      [ESP32]       [Windows]     [Linux]
   VAD+stream     VAD+WW+UI      terminal
              Satelity — cienkie klienty
```

**Kluczowe właściwości docelowego centrum:**
- Controller i Worker to **oddzielne serwisy** komunikujące się przez HTTP — nawet jeśli siedzą na tej samej maszynie. Separacja odpowiedzialności jest zachowana.
- Mini PC jest zawsze włączony → Butler (1.5B fallback) staje się zbędny → jeden model, jedna jakość.
- `node` na Windows traci komponent Worker → staje się czystą Satelitą z UI.
- RPi5 nie ma roli w tej architekturze.

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

Gdy Satelita z pomieszczenia `salon` wysyła żądanie, Kontroler **nie podaje modelowi pełnej listy urządzeń domowych**. Zamiast tego filtruje ją do urządzeń przypisanych do pokoju `salon` i buduje dla modelu wąski, precyzyjny kontekst. Model 1.5B operuje wtedy na liście 5 urządzeń zamiast 50 — to nie jest ograniczenie, to jest precyzja.

**Otwarta kwestia — cross-room commands:** Co gdy użytkownik w salonie mówi "wyłącz światło w sypialni"? Propozycja: model dostaje domyślnie swój pokój, ale posiada narzędzie `get_devices(room=...)` pozwalające mu sięgnąć po inne pomieszczenie gdy wyraźnie o to prosi. Większy model na desktopie może od razu otrzymywać pełną listę urządzeń. **Nierozstrzygnięte — wymaga dalszej dyskusji.**

### Co Kontroler synchronizuje do Węzłów
Kontroler przechowuje i dystrybuuje:
- **Prompty systemowe** — tożsamość Regisa, instrukcje behawioralne (rdzeń persony)
- **Historia konwersacji** — aktywne sesje, umożliwia migrację kontekstu między węzłami
- **Rejestr wszystkich encji** — lista aktywnych Satelit i Węzłów z metadanymi

---

## 5. Dwa Tryby Pracy (Przejściowy Kompromis Sprzętowy)

Dwa tryby pracy **nie są świadomą decyzją projektową — są chwilowym kompromisem wynikającym z ograniczeń sprzętowych.** RPi5 nie jest w stanie uruchomić modelu 9B. Gdyby mógł, nie byłoby podziału na tryby — istniałby jeden model, jedno centrum.

Butler (1.5B) pełni rolę **ostatniej linii obrony**: działa gdy żaden mocniejszy węzeł nie jest dostępny. Nie jest równorzędną alternatywą dla Regis Agent — jest fallbackiem.

**Stan obecny (konfiguracja przejściowa):**

| | Regis-Baseline (1.5B, RPi5) | Regis-Agent (9B, Desktop) |
|---|---|---|
| **Model** | Qwen 2.5 1.5B Instruct *(planowana migracja na Qwen 3.5)* | Qwen 3.5 9B |
| **Rola** | Deterministyczny parser komend — fallback | Myślący agent z pętlą ReAct — cel |
| **Dostępność** | 24/7, zawsze | Tylko gdy węzeł Windows jest włączony |
| **Zakres** | Komendy urządzeń z danego pokoju | Pełny zakres narzędzi i rozmowa |
| **Odpowiedź poza zasięgiem** | *"To przekracza moje obecne możliwości."* — zwięźle | Obsługuje |

**Cel docelowy:** jeden model (9B+) na dedykowanym centrum, dostępny 24/7. Patrz §3.6.

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
- Auto-Discovery węzłów (UDP Broadcast Zero-Conf, `core/discovery.py`)
- Rejestr Encji (Satelity i Węzły rejestrują się w Kontrolerze)

**Aktualny dług (oczekuje realizacji):**
- **Dystrybucja Windows:** Inno Setup (`RegisNodeSetup.exe`) jest zaprojektowany (`docs/distribution_rfc.md`) ale instalator nie jest jeszcze zbudowany produkcyjnie — patrz `TASKS.md`.
- **Pamięć Długoterminowa:** Stary system Notatnika wycięty. Nowe rozwiązanie (np. wektorowe) nie zostało jeszcze zaprojektowane — patrz `TASKS.md`.
- **Dead code `frozen`:** `core/config.py` zawiera pozostałość po epoce PyInstaller (`if getattr(sys, 'frozen', False)`). Do usunięcia w oddzielnej sesji.
