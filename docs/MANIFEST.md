# Regis: Manifest Projektu

Ten dokument definiuje duszę projektu Regis. Służy jako najwyższy kompas dla programistów oraz agentów AI pracujących przy kodzie. Jeśli jakakolwiek nowa funkcja, narzędzie lub decyzja architektoniczna jest sprzeczna z tym dokumentem — należy ją odrzucić.

---

## 1. Czym jest Regis?

Regis to **autonomiczne oprogramowanie agenta** — instalujesz je na dedykowanym sprzęcie (np. RPi5, mini PC) i od razu otrzymujesz działający system z własnym panelem webowym. Otwierasz przeglądarkę, widzisz dashboard: status węzłów, satelit, aktywnych sesji i integracji. Integracje dodajesz **do Regisa** — nie na odwrót.

Regis nie jest frameworkiem ani biblioteką. Jest produktem — tak jak Home Assistant jest produktem do smart home, Regis jest produktem do prowadzenia agenta w złożonym środowisku osobistym i domowym. Jego rdzeń to pełnoprawny agent (pętla ReAct, zarządzanie sesjami, rejestr narzędzi) z pluginowalną warstwą zmysłów (LLM, STT, TTS, kanały komunikacji) i opcjonalnymi integracjami narzędziowymi (HA, web, kamery). Możesz go rozszerzyć — ale działa i bez żadnych rozszerzeń.

**Istota projektu:** Regis to oprogramowanie które interaktuje z innymi oprogramowaniami w dokładnie taki sam sposób jak człowiek. Nie interesuje go low-level — protokoły, sterowniki, sposób w jaki żarówka Zigbee negocjuje połączenie z koncentratorem. Regis widzi to co widzi człowiek patrzący na dashboard: włączona lub wyłączona. Dlatego Home Assistant — platforma z setkami integracji i całym ekosystemem community — jest z perspektywy Regisa po prostu jedną integracją w katalogu `integrations/`. Regis nie zarządza urządzeniami. Pyta systemy które to robią. To jest właściwy poziom abstrakcji, nie ograniczenie.

Regis jest projektem osobistym — zaprojektowanym do poruszania się w złożonym środowisku domowym i osobistej przestrzeni użytkownika. Nie jest narzędziem enterprise. Nie służy do scrapowania internetu, przetwarzania tysięcy dokumentów ani obsługi korporacyjnych procesów — choć agent ReAct technicznie byłby do tego zdolny. Fakt że coś jest możliwe, nie znaczy że powinno tu trafić. Regis to asystent z osobowością, nie platforma do automatyzacji.

Projekt jest hobby — jakość, spójność i czystość architektury są ważniejsze niż szybkie dostarczanie funkcji.

---

## 2. Złota Zasada: Przezroczystość (Zasada "Nie Przeszkadzaj")

**System musi być organiczny i nigdy nie może wchodzić użytkownikowi w drogę.**

Największym grzechem w tym projekcie jest implementacja funkcji "na siłę", tylko dlatego, że technologia na to pozwala. Jeśli nowa funkcjonalność (nawet najbardziej zaawansowana technologicznie) sprawia, że system staje się uciążliwy, wolny lub irytujący — należy ją usunąć lub całkowicie przeprojektować. W najgorszym scenariuszu Regis ma być po prostu **niewidzialny i bezkolizyjny** dla domowników.

---

## 3. Model Architektury — Trójwarstwowy

Architektura Regisa dzieli się na trzy warstwy o ściśle zdefiniowanych rolach i granicach. Każda warstwa komunikuje się z warstwą wyżej wyłącznie przez abstrakcyjne interfejsy — nigdy bezpośrednio przez konkretne implementacje.

### 3.1 Warstwa 1 — Core (Układ Nerwowy)

Core to wszystko, co stanowi samego agenta. Instalując Regisa, dostajesz kompletny mózg i układ nerwowy — gotowy do działania po podłączeniu zmysłów. Core nie wymaga konfiguracji, żeby *istnieć* — wymaga podłączonych providerów, żeby *działać*.

**Zawartość:**
- **Pętla ReAct** — wewnętrzny monolog `<thought>`, routing narzędzi, obsługa tury konwersacji
- **Session Manager** — historia konwersacji per sesja, przechowywanie i odtwarzanie kontekstu
- **Tool Registry** — mechanizm rejestracji i wywoływania narzędzi (nie konkretne narzędzia — tylko mechanizm)
- **Abstrakcyjne interfejsy dla zmysłów:**
  - `ILLMProvider` — gniazdo na model językowy
  - `ISTTProvider` — gniazdo na transkrypcję mowy
  - `ITTSProvider` — gniazdo na syntezę mowy
  - `ISatellite` — gniazdo na kanał komunikacji z użytkownikiem
- **Protokół wewnętrzny** — schematy i kontrakty komunikacyjne między komponentami

**Zasada:** Core nie zawiera żadnych referencji do konkretnych providerów, satelit ani narzędzi. Wie tylko, że *coś* implementuje dany interfejs.

**Walidacja przy starcie:** Przynajmniej jedno `ILLMProvider` musi być podłączone. Bez LLM agent nie funkcjonuje — to fundamentalne wymaganie, inaczej niż brak narzędzi (bez integracji HA agent po prostu nic nie może *zrobić* w smart home, ale nadal istnieje).

### 3.2 Warstwa 2 — Providers & Channels (Zmysły i Ręce)

Wymienna cybernetyka agenta. Konkretne implementacje podłączane do interfejsów Core przy starcie. Bez warstwy 2 Core istnieje, ale nie funkcjonuje. Zmiana providera STT nie wymaga dotknięcia Core — wymaga jedynie zamiany implementacji w tej warstwie.

| Interfejs | Przykładowe implementacje |
|---|---|
| `ILLMProvider` | OpenRouter, Ollama, Anthropic API |
| `ISTTProvider` | Faster-Whisper (lokalny), Cloud STT API |
| `ITTSProvider` | Piper (lokalny), Cloud TTS API |
| `ISatellite` | ESP32, terminal, HTTP API |

**Regis Desktop** jest szczególnym przypadkiem warstwy 2 — to **menedżer usług** który bundluje wiele implementacji warstwy 2 w jednej aplikacji: satelitę (`ISatellite`), lokalny LLM (`ILLMProvider`), lokalne STT (`ISTTProvider`) i lokalne TTS (`ITTSProvider`). Każda z tych usług rejestruje się w Regisie niezależnie. Użytkownik może włączyć lub wyłączyć konkretne usługi — np. uruchomić tylko STT i TTS lokalnie, a LLM pozostawić w chmurze.

**Kluczowa właściwość:** Warstwa 2 jest wymienialna bez zmian w Core i bez zmian w warstwie 3. Możesz dołożyć nową satelitę (np. aplikację mobilną) i żaden istniejący kod poza warstwą 2 nie wymaga modyfikacji.

### 3.3 Warstwa 3 — Integrations (Narzędzia)

Konkretne zdolności agenta do działania w świecie zewnętrznym. W pełni opcjonalne — agent funkcjonuje bez żadnej integracji, po prostu nie może nic *zrobić* poza rozmową.

**Mechanizm:** Każda integracja rejestruje swoje narzędzia w `ToolRegistry` przy starcie. Core nie wie skąd narzędzia pochodzą — widzi tylko ich sygnatury i wywołuje je przez abstrakcję.

**Przykłady:** Home Assistant (smart home), przeglądarka internetowa, kamery IP, MQTT, własne skrypty, dowolny endpoint z sensownym zastosowaniem.

**Dodanie nowej integracji:** nowy katalog w `integrations/`, rejestracja narzędzi w `ToolRegistry`. Żadne inne warstwy nie wymagają zmian.

### 3.4 Diagram

```
┌───────────────────────────────────────────────────────┐
│  WARSTWA 1 — CORE (Układ Nerwowy)                     │
│                                                       │
│  [ReAct Loop]    [Session Manager]    [Tool Registry] │
│       │                                    │          │
│  [ILLMProvider] [ISTTProvider] [ITTSProvider] [ISatellite]
└───────────────────────┬───────────────────────────────┘
                        │ abstrakcyjne interfejsy
         ┌──────────────┴──────────────────┐
         ▼                                 ▼
┌──────────────────────┐   ┌───────────────────────────┐
│  WARSTWA 2           │   │  WARSTWA 3                │
│  Providers &         │   │  Integrations (Narzędzia) │
│  Channels            │   │                           │
│                      │   │  Home Assistant           │
│  OpenRouter / Ollama │   │  Web / Pliki / Kamery     │
│  Whisper / Cloud STT │   │  MQTT / własne API        │
│  Piper / Cloud TTS   │   │  ...                      │
│  ESP32 / Desktop     │   │                           │
│  Terminal / HTTP API │   │                           │
└──────────────────────┘   └───────────────────────────┘
```

---

## 3.5 Referencyjna Implementacja (Przykładowy Deployment)

> Poniższe sekcje opisują **konkretną implementację referencyjną** — nie definicję systemu. RPi5, Windows Node i ESP32 to implementacje warstwy 2. Architektura Regisa jest od nich niezależna i może być wdrożona na innym sprzęcie lub z innymi kanałami komunikacji.

### Kontroler (`controller`)
- **Rola:** Mózg systemu i jedyne źródło prawdy. Zarządza rejestrem aktywnych węzłów roboczych, routingiem sesji oraz wykonywaniem narzędzi Home Assistant.
- **Deployment:** Zawsze i tylko Raspberry Pi 5 (Linux). Singleton — może istnieć dokładnie jedna instancja. Dystrybuowany jako pakiet `.whl`.
- **Kluczowa zasada:** Kontroler to lekki daemon — nigdy nie hostuje modelu LLM. Jest jedynym punktem komunikacji z Home Assistant; węzły robocze nigdy nie mają dostępu do HA bezpośrednio.
- **Routing:** Kontroler wybiera najlepszy dostępny węzeł (preferuje wyższy tier) dla każdej nowej sesji. Graceful migration między aktywnymi sesjami nie jest zaimplementowana — system działa na zasadzie best-effort.

### Węzeł roboczy (`worker`) — Linux / RPi5
- **Rola:** Zawsze uruchomiony na RPi5 komponent bezpieczeństwa systemu. Hostuje dwa serwisy offline:
  1. **Parser offline** — lekki model zdolny do pracy na RPi5, z Structured Outputs. Obsługuje proste komendy urządzeń gdy żaden pełny provider LLM nie jest dostępny.
  2. **Awaryjny STT** — lekki model Whisper do transkrypcji audio w trybie offline.
- **Deployment:** Pakiet `.whl` instalowany przez `pip` na RPi5 (Linux). Brak UI — czysty serwer HTTP.
- **Uwaga:** RPi5 nie ma podłączonego mikrofonu — **nie nagrywa dźwięku samodzielnie**. STT działa wyłącznie na danych strumieniowanych przez Satelity.
- **Status:** Parser i awaryjny STT są ostatnią linią obrony — aktywowane gdy system przechodzi w tryb fallback (brak przynajmniej jednego providera spośród STT, LLM, TTS). Nie są częścią normalnej ścieżki produkcyjnej.

### Regis Desktop (Menedżer Usług Warstwy 2) — Windows PC
- **Rola:** Pełnoprawna **aplikacja Windows** z interfejsem terminalowym. Jest menedżerem usług bundlującym wiele implementacji warstwy 2 w jednej aplikacji: satelitę (VAD, WakeWord, audio I/O), lokalny worker LLM (Ollama), lokalne STT (Faster-Whisper) i lokalne TTS (Piper). Każda z tych usług rejestruje się w Regisie niezależnie — użytkownik może włączać i wyłączać konkretne usługi wedle potrzeb.
- **Deployment:** Dystrybuowany jako **Windows Installer** (`RegisDesktopSetup.exe`, Inno Setup) — wymaga Python zainstalowanego w systemie.
- **Rola producencyjna:** Opcjonalna. W typowej produkcji Regis Desktop nie jest uruchomiony — system korzysta z providerów chmurowych. Gdy jest aktywny, automatycznie rejestruje się jako lokalny provider STT, LLM i TTS.
- **Główne zastosowania:** Środowisko deweloperskie (lokalny LLM, tańszy STT/TTS), awaryjny fallback gdy chmura jest niedostępna.
- **Koegzystencja:** Worker LLM i Satellite mogą działać jednocześnie — nie wykluczają się.

### Satelita — typy interfejsów
Każdy interfejs użytkownika jest architektonicznie Satelitą — różnią się medium:
  - **ESP32** — miniaturowy, dedykowany sprzęt w domu; robi VAD i strumieniowanie audio. Tani, niskoprądowy, idealny do stałego montażu.
  - **Windows PC** (`node`) — aplikacja z UI terminalowym; robi VAD + WakeWord lokalnie, resztę deleguje do centrum.
  - **Linux** — wariant headless lub terminalowy.

### Pipeline Przetwarzania Audio (Rozstrzygnięte)

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

## 3.6 Warstwa Integracji (Rozstrzygnięta Zasada Architektoniczna)

**Home Assistant jest jedną z możliwych integracji — nie jedyną.**

Katalog `integrations/` to granica między logiką systemu a światem zewnętrznym. HA jest pierwszą i prawdopodobnie największą integracją (żarówki, przełączniki, klimatyzacja, odtwarzacze — wszystko co najłatwiej podłączyć przez HA), ale architektura nie zakłada jego wyłączności.

Przyszłe integracje mogą obejmować m.in.:
- Bezpośrednia komunikacja MQTT
- Inne platformy Smart Home (np. Zigbee2MQTT)
- Własne skrypty i usługi sieciowe
- Dowolny inny endpoint, który ma sens w kontekście sterowania domem

**Konsekwencja dla kodu:** `ToolsRegistry` i `RemoteToolsRegistry` są agnostyczne wobec źródła narzędzi — rozmawiają z `integrations/` przez abstrakcyjny interfejs, nie bezpośrednio z HA. Dodanie nowej integracji oznacza: nowy plik w `integrations/`, nowe narzędzie w `protocol/schemas.py` i nowy handler w `protocol/tools_registry.py`. Żadne inne warstwy nie wymagają zmian.

---

## 3.7 Wizja Docelowa

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

## 6. Persona Agenta

### Persona jest user-defined

System Regis nie narzuca konkretnego charakteru, tonu ani stylu agenta — to jest konfiguracja użytkownika. Użytkownik definiuje personę w pliku konfiguracyjnym (imię, charakter, instrukcje behawioralne). Regis dostarcza mechanizm — nie treść.

**Zasada spójności:** Cokolwiek użytkownik skonfiguruje jako personę, system musi ją utrzymywać konsekwentnie we wszystkich trybach pracy i na wszystkich węzłach. Persona zdefiniowana przez użytkownika nie może się zmieniać w zależności od tego, który model LLM aktualnie pracuje pod spodem.

### Cele projektowe systemu (nie persony)

Regis jako oprogramowanie ma następujące **cele projektowe** — nie są to twierdzenia o aktualnym stanie, lecz intencje które powinny kierować każdą decyzją architektoniczną i UX:

- **Szybkość** — minimalne opóźnienia między wejściem użytkownika a odpowiedzią systemu
- **Bezpośredniość** — brak zbędnych kroków pośrednich, warstw abstrakcji które nie wnoszą wartości
- **Niezawodność** — system działa albo jawnie informuje o problemie; stany częściowe i ciche błędy są niedopuszczalne

### Implementacja spójności persony między trybami
- **Konfigurowalny rdzeń persony:** W każdym prompcie, niezależnie od trybu i tieru, osadzony jest opis persony zdefiniowanej przez użytkownika. Tryb pracy (NLU vs ReAct) zmienia się — persona nie.
- **Graceful Degradation:** Agent nigdy nie udaje, że potrafi czegoś, czego nie potrafi. Odpowiada zwięźle i bez przepraszania. Brak tłumaczeń technicznych.
- **Capability Layer (Warstwa Możliwości):** Prompty pisane są warstwowo. Rdzeń persony jest stały. Zestaw narzędzi i tryb pracy zmienia się w zależności od dostępnych providerów.

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
- **Formalne interfejsy warstwy 2:** Abstrakcyjne interfejsy `ILLMProvider`, `ISTTProvider`, `ITTSProvider`, `ISatellite` istnieją jako koncepcja architektoniczna (§3.1) — nie są jeszcze sformalizowane jako klasy bazowe w kodzie. Implementacja jest częścią `[ARCH — Phase 2]`.
