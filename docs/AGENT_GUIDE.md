# Regis: Przewodnik dla Agentów AI

Ten dokument jest przeznaczony wyłącznie dla agentów AI (LLM) pracujących nad projektem. Odpowiada na pytanie: *jak myśleć o tym projekcie*, a nie tylko co w nim jest.

---

## Hierarchia Lektury (Kolejność ma Znaczenie)

Przed podjęciem JAKIEJKOLWIEK pracy wykonaj lekturę w tej kolejności:

1. **`docs/MANIFEST.md`** — Przeczytaj uważnie i zrozum. To jest najważniejszy plik w projekcie. Definiuje filozofię, cele i rozstrzygnięte decyzje projektowe. Jeśli jakakolwiek Twoja propozycja jest sprzeczna z tym dokumentem — jest zła, niezależnie od tego jak technicznie poprawna.
2. **`.agents/HANDOFF.md`** — Stan projektu po ostatniej sesji. Co zostało zrobione, co jest zepsute, od czego zacząć.
3. **`.agents/TASKS.md`** — Lista aktywnych zadań.
4. **`docs/ONBOARDING.md`** — Sięgaj po ten dokument gdy musisz zrozumieć konkretny plik lub mechanizm. Nie musisz go czytać w całości na starcie.

---

## Hierarchia Autorytetu w Decyzjach

Gdy stoisz przed decyzją projektową lub architektoniczną, stosuj następującą kolejność:

```
MANIFEST.md (filozofia)
    ↓
Wyraźna instrukcja użytkownika w tej sesji
    ↓
Decyzje z HANDOFF.md (poprzednie sesje)
    ↓
Twój osąd techniczny
```

Jeśli Twój osąd techniczny sugeruje coś innego niż MANIFEST.md — nie wcielaj swojego pomysłu w życie. Zamiast tego zaprezentuj go użytkownikowi jako propozycję, wyraźnie zaznaczając że wymaga to przeglądu zasad projektowych.

---

## Protokół Eskalacji Decyzji Architektonicznych

Nie istnieje oddzielna rola "Agenta Architekta". Każdy agent — niezależnie od tego czy zajmuje się kodem czy dokumentacją — stosuje ten sam protokół gdy natrafi na decyzję wykraczającą poza jego bieżące zadanie.

**Kiedy zatrzymać pracę i zaeskalować:**
- Odkrywasz, że realizacja zadania wymaga zmiany w filozofii projektu (MANIFEST.md).
- Napotykasz sprzeczność między tym, co zadanie nakazuje, a tym co mówi MANIFEST.md.
- Odkrywasz błąd projektowy — nie implementacyjny.
- Masz do wyboru dwa podejścia techniczne prowadzące do fundamentalnie różnych ścieżek architektonicznych.

### Ostrzeżenie: Skażenie Kontekstu (Context Contamination)

Po kilkunastu turach intensywnej pracy nad kodem Twój kontekst jest wypełniony liniami kodu, stack trace'ami i błędami parsowania. To **fizycznie degraduje Twoją zdolność do myślenia architektonicznego**. Nie jesteś w stanie tego poczuć — po prostu proponujesz rzeczy, które wydają Ci się sensowne z perspektywy zaśmieconego kontekstu. Propozycje architektoniczne z takiego stanu często tworzą dług techniczny.

**Zasada:** Im dłuższa sesja kodowania, tym mniej ufaj swojej własnej ocenie w kwestiach architektonicznych.

### Mechanizm: Czysty Architectural Handoff

Gdy natrafiasz na decyzję architektoniczną w trakcie sesji kodowania — **nie próbuj jej rozwiązywać w bieżącym kontekście**. Zamiast tego wyekstrahuj istotę problemu do `HANDOFF.md` w standardowym formacie i zakończ sesję. Użytkownik otworzy świeżą rozmowę dedykowaną tej jednej kwestii.

**Format wpisu w HANDOFF.md:**
```
## DECYZJA_ARCHITEKTONICZNA — Wymagana Nowa Sesja
Kontekst: [co robiłem gdy to odkryłem — 1-2 zdania]
Problem: [jaka decyzja wymaga podjęcia — konkretnie i precyzyjnie]
Opcja A: [opis]
Opcja B: [opis]
Moja obserwacja: [UWAGA: mój kontekst jest skażony kodem — nie ufaj tej ocenie w pełni]
```

Twoja wartość jako agenta kodującego polega na tym, że rozumiesz techniczny kontekst problemu. Twój obowiązek to wyekstrahowanie tej wiedzy do czystego dokumentu — nie podejmowanie decyzji.

**Czego NIE robić:**
- Nie podejmuj decyzji architektonicznych samodzielnie, nawet jeśli jesteś "prawie pewien".
- Nie implementuj rozwiązania tymczasowego "na teraz" zakładając że ktoś to poprawi — tymczasowe rozwiązania żyją wiecznie.
- Nie pomijaj eskalacji z powodu "nie chcę przerywać" — architektoniczny błąd jest droższy niż przerwa.

---

## Prawa Zapisu do Dokumentów

Każdy agent ma pełny odczyt do wszystkich dokumentów. Prawa zapisu są następujące:

| Dokument | Agent pracujący nad kodem | Uwagi |
|---|---|---|
| `.agents/HANDOFF.md` | Zawsze aktualizuje | Obowiązkowe na końcu każdej sesji |
| `.agents/TASKS.md` | Zawsze aktualizuje | Odhaczaj ukończone zadania |
| `docs/ONBOARDING.md` | Może aktualizować | Tylko fakty — nowe pliki, zmieniona struktura. Nigdy filozofia. |
| `docs/MANIFEST.md` | Tylko po decyzji użytkownika | Zmiany wyłącznie jako efekt rozmowy z użytkownikiem |
| `docs/AGENT_GUIDE.md` | Tylko po decyzji użytkownika | Jak wyżej |

**Zasada prosta:** Dokumenty operacyjne (HANDOFF, TASKS) — aktualizujesz sam. Dokumenty filozoficzne (MANIFEST, AGENT_GUIDE) — tylko jako efekt decyzji podjętej z użytkownikiem w tej sesji. ONBOARDING.md jest pośrodku — fakty tak, filozofia nie.

---

## Decyzje Już Podjęte (Nie Otwieraj Ponownie)

Poniższe decyzje były świadomie przemyślane i rozstrzygnięte. Propozycja ich zmiany bez wyraźnej prośby użytkownika jest błędem.

| Decyzja | Powód |
|---|---|
| Narzędzia renderowane jako tekst XML w prompcie (`<tools>`), nie jako pole `tools` w API Ollamy | "Droga A" — eliminuje wstrzykiwanie przez Ollamę angielskiego bloku instrukcji, które powoduje "angielski drift" w odpowiedziach modelu |
| Stop Token `</action>` w API Ollamy | Wymusza liniową pętlę ReAct. Bez tego modele Qwen halucynują równoległe wywołania |
| Parser offline (RPi5) używa Structured Outputs (JSON Schema), nie ReAct | Model jest zbyt mały na niezawodny ReAct. JSON Schema wymusza deterministyczne parsowanie komend |
| Pozytywne ramowanie w promptach zamiast zakazów | Negative framing degraduje zdolności kognitywne małych modeli |
| System jest agnostyczny wobec providera (LLM, STT, TTS) — chmura i local to równorzędne opcje | Architektura nie zakłada wyłączności żadnego backendu. Wymiana providera nie wymaga zmian poza warstwą abstrakcji |
| Parser offline (RPi5) jest offline fallbackiem — nie siedzi w ścieżce krytycznej gdy internet działa | Parser-first generował opóźnienie dla każdego zapytania które on odrzucał. Chmurowy LLM obsługuje proste komendy równie dobrze i szybko |
| OpenRouter jest domyślnym providerem LLM w produkcji — preferowane modele OSS | Ekonomika: cloud API jest tańszy niż dedykowany sprzęt lokalny przy obecnych cenach RAM i GPU |
| Dwustanowa degradacja: pełny tryb gdy komplet providerów, fallback gdy brakuje choćby jednego | Prostota i przewidywalność. Stany częściowe (np. LLM bez TTS) tworzą nieintuicyjne zachowania |
| Ascetyczny styl CLI (bez jaskrawych kolorów, minimalne emoji) | Zasada estetyczna projektu. Opisana w `AGENTS.md` |
| Historia konwersacji przechowuje tylko pełne tury (user+assistant), nie ślad ReAct | Ślad ReAct (myśli + wywołania) zaśmieca kontekst i powoduje amnezję przy długich sesjach |
| Dystrybucja Windows = Inno Setup Installer + Python systemowy (nie PyInstaller) | PyInstaller odrzucony: black box, podejrzany wygląd, opóźnienia startu. Szczegóły: `docs/distribution_rfc.md` |
| `controller.worker` na RPi5 hostuje Parser offline i awaryjny STT — nie jest production LLM workerem | RPi5 pełni rolę centrum bezpieczeństwa (last resort). Produkcyjny LLM pochodzi od providera (cloud lub Windows Node). |

---

## Filozofia Wynikająca z MANIFEST.md (Tłumaczenie na Praktykę)

**"Nie Przeszkadzaj"** oznacza w praktyce dla agenta:
- Nie dodawaj funkcji, o które nie proszono.
- Nie dodawaj walidacji, logów czy obsługi błędów "dla bezpieczeństwa" jeśli nie jest to wymagane.
- Nie upiększaj kodu jeśli działa. Refaktoryzuj tylko gdy wprost polecono.
- Nie proponuj złożonych rozwiązań tam gdzie proste wystarczy.

**"Jakość ponad tempo"** oznacza dla agenta:
- Lepiej zadać pytanie niż zgadnąć intencję i zaimplementować coś złego.
- Lepiej zaplanować i przedstawić plan do akceptacji niż pisać kod który trzeba będzie cofać.

---

## Architektura LLM — Co Musisz Rozumieć

Ten projekt ma dwa fundamentalnie różne tryby pracy modelu. **Tier to pojęcie promptu i zdolności modelu — nie mechanizm routingu.** Kontroler wybiera providera na podstawie dostępności (patrz §5 MANIFEST.md), nie na podstawie tieru. Pomylenie trybów pracy przy modyfikacji promptów jest krytycznym błędem.

### Tryb NLU — tier `butler` (lekki model na RPi5)
- Model działa jak **klasyczny parser intencji**.
- Nie używa pętli ReAct ani wewnętrznego monologu `<thought>`.
- Dostaje krótki prompt z przykładami Few-Shot i zwraca deterministycznie JSON zgodny ze schematem narzuconym przez Ollamę (JSON Schema / Structured Outputs).
- Prompt w `data/prompts/tier_butler.md` jest ekstremalnie uproszczony. Celowo.
- **Nie dodawaj do niego ReAct-owych instrukcji.** Nie obsłuży ich i zepsuje się.

### Tryb ReAct — tier `regis` (domyślnie: OpenRouter cloud, awaryjnie: Ollama lokalnie)
- Model działa jako **pełnoprawny agent** z pętlą Reasoning → Acting.
- Obowiązkowo używa tagu `<thought>...</thought>` do wewnętrznego rozumowania przed każdą akcją.
- Pętla trwa dopóki model wywołuje narzędzia. Gdy nie wywołuje — to jest finalna odpowiedź.
- Model widzi historię jako serie tur (user + assistant), nie jako surowy ślad rozumowania.
- **Nie skracaj promptu** — modele ReAct potrzebują szczegółowych instrukcji, checklist i przykładów Few-Shot.

---

## Konwencje Kodu i Styl

- **Język:** Polski dla wszystkich stringów widocznych dla użytkownika, komentarzy w kodzie i promptów systemowych. Angielski jest akceptowalny dla nazw zmiennych, funkcji i klas.
- **CLI:** Biblioteka `rich`. Stosuj `[dim]` dla tekstów pomocniczych, `[bold white]` dla nagłówków. Unikaj `cyan`, `yellow`, `magenta` jako kolorów dekoracyjnych. Czerwony dla błędów, zielony dla sukcesów — i nic więcej.
- **PowerShell:** Używaj `;` zamiast `&&` do łączenia komend. System to Windows.
- **Testy:** `pytest`. Uruchamiaj przed zgłoszeniem zakończenia zadania.

---

## Typowe Błędy Agentów w Tym Projekcie

Lista błędów, które agenty popełniają regularnie w tym projekcie:

1. **Proponowanie natywnego `tools` API Ollamy** — odrzucone. Patrz tabela wyżej ("Droga A").
2. **Dodawanie emoji do CLI** — sprzeczne z estetyką projektu.
3. **Pisanie kodu bez polecenia** — projekt ma zasadę "żadnych zmian bez wyraźnego nakazu". Jeśli nie jesteś pewien czy masz pozwolenie — zapytaj.
4. **Implementowanie "Drogi B" (ciężki fallback parser) dla słabszych modeli** — filozofia projektu zabrania ratowania słabych modeli skomplikowanym kodem. Jeśli model nie działa, zmień model lub zmień prompt.
5. **Tight-coupling do konkretnego providera LLM/STT/TTS** — system jest agnostyczny wobec backendu. Wywołania bezpośrednio do OpenRouter lub Ollamy poza warstwą abstrakcji są błędem. Każdy provider musi implementować wspólny interfejs.
6. **Refaktoryzacja bez zgody** — zmiana struktury kodu wymaga planu i akceptacji, nie jest "przy okazji".
7. **Ignorowanie hardcode'owanych adresów IP** — są świadomie tymczasowe. Nie "naprawiaj" ich bez polecenia.
8. **Brak izolacji przy tworzeniu konfiguracji** — architektura znajduje się obecnie w trakcie ewolucji z powodu długu dystrybucyjnego. Scentralizowane pliki z `data/` (jak `settings.json`) powodują konflikty podczas deploymentu i są wycofywane na rzecz specyficznych profili (`settings.<PROFILE>.json`) lub lokalnych zmiennych `.env`. Zapoznaj się z raportem `docs/architectural_debt_report.md` zanim zaczniesz rzeźbić w ogólnej konfiguracji.

---

## Wskazówki do Pracy z Promptami Modeli

Gdy modyfikujesz pliki w `data/prompts/`:

- **Zachowaj strukturę wypunktowaną.** Modele Instruct reagują lepiej na listy niż na akapity prozy.
- **Sandwiching działa.** Kluczowe zasady powtarzaj zarówno na początku jak i na końcu promptu.
- **Nie używaj negatywnego framingu.** Zamiast "Nie wywołuj narzędzi bez myśli" napisz "Zawsze zacznij od bloku `<thought>` przed każdą akcją".
- **Few-Shot przykłady muszą być kontrastujące.** Jeden przykład pokazujący użycie narzędzia, jeden przykład pokazujący odpowiedź BEZ narzędzia. Model musi widzieć oba wzorce.
- **Testuj na modelu docelowym.** Prompt zoptymalizowany pod duży model chmurowy często zepsuje lekki parser na RPi5 i odwrotnie.
