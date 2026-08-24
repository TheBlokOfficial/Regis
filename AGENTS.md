# AGENTS.md — System Regis

## Kontekst
Architektura/decyzje projektowe: `docs/manifest.md`, `docs/onboarding.md`.
Jeśli w pamięci projektu (auto memory) nie ma jeszcze notatek o
architekturze: przeczytaj raz oba pliki i zapisz kluczowe fakty do pamięci.
Jeśli notatki już tam są — korzystaj z nich zamiast wczytywać pliki od
nowa; wróć do źródeł tylko przy realnej niejasności.

## Zasady pracy
- Nie zgaduj: sprawdź realne ścieżki, nazwy funkcji, schematy danych zamiast
  zakładać.
- Po zmianie uruchom dostępny test/build/lint — nie zakładaj, że "wygląda
  na gotowe".
- Zmiana obejmująca >3 pliki lub nieznany fragment kodu: zarysuj krótko plan
  przed edycją. Dla mniejszych poprawek działaj od razu.
- Widzisz lukę w pomyśle albo lepsze rozwiązanie? Zgłoś to zamiast wdrażać
  bezrefleksyjnie.

## Architektura: kierunek zależności (najłatwiejsza do złamania reguła)
Kernel (`server/agent/`) **nie zna z góry konkretnej implementacji** silnika
świata — zna wyłącznie minimalny protokół `WorldInterface`
(`agent/context_provider.py`), dokładnie tak jak zna `BaseLLMProvider` zamiast
konkretnego dostawcy LLM. Jedyny konkretny silnik, `server/world/`
(`WorldEngine`), wstrzykiwany jest jawnie w kompozycji aplikacji (`main.py`).

Od 2026-08-24 protokoły dostawców AI (`BaseLLMProvider`, `BaseSTTProvider`,
`BaseTTSProvider`, `WakeWordDetector`) mieszkają w `server/ports/` — między
konsumentem a konkretem. Wcześniej stały u konsumenta, przez co `ai/` musiało
importować go z powrotem; powstawały cykle łatane leniwymi importami.
`WorldInterface` **zostaje** w `agent/context_provider.py`, bo `world -> agent`
jest jednokierunkowe i cyklu tam nie ma.

```bash
grep -rn "from server.world" services/server/src/server/agent/
grep -rn "from server.voice" services/server/src/server/ai/
grep -rn "from server.agent" services/server/src/server/ai/
```
(poprawny wynik każdej: brak trafień — to granice, które muszą zostać nienaruszone)

**Świadomie porzucona generyczność**: wcześniejszy model "N niezależnych,
wzajemnie nieświadomych rozszerzeń" (`PluginProvider`/`Gateway`/
`NetworkExtension`, warstwa `server/extensions/`) został zniesiony — bronił
się przed scenariuszem (podmiana/wielość rozszerzeń), który w tym prywatnym,
jednoosobowym projekcie nigdy się nie wydarzy. `WorldEngine` woła swoje
wewnętrzne backendy (`HomeAssistantClient`, rejestr satelit) wprost, zwykłymi
wywołaniami metod — zero protokołu między nimi. Nie ma już koncepcji
"wyłączenia rozszerzenia" — backend albo działa, albo zwraca błąd w locie
(np. zły token), nigdy osobny boolean `enabled`. Nie odtwarzaj generycznej
wielorozszerzeniowości bez konkretnego, realnego drugiego silnika w ręku
(patrz `docs/manifest.md`, sekcja "Świadome decyzje projektowe").

Uzasadnienie i konsekwencje: `docs/manifest.md`, sekcje 3 i 5.

## Jakość kodu
- SOLID, DRY, KISS, YAGNI, Boy Scout Rule.
- Ścisłe typowanie: pełne adnotacje typów w sygnaturach funkcji i metod.
- Logowanie przez wspólny helper: `logger = get_logger("regis.nazwa_modułu")`.
- Warstwa REST jest cienka: przyjmuje żądanie, woła domenę, tłumaczy wyjątek
  domenowy na kod odpowiedzi. Reguły biznesowe („pominięte pole zachowuje obecną
  wartość" itp.) należą do domeny — obowiązują każdego wywołującego, nie tylko HTTP.
- Przed commitem, komplet:
  ```bash
  python -m uv run ruff check .
  python -m uv run mypy
  python -m uv run python -m pytest -q
  ```
  Stan oczekiwany: ruff bez trafień, mypy bez błędów, wszystkie testy zielone.
  Oba narzędzia raportują, nie blokują — ale zostawianie po sobie nowych trafień
  jest cofaniem się.

## Dokumentacja
`docs/` dzieli się na dwie kategorie o różnym cyklu życia — nie myl ich:

- **Dokumenty trwałe** (`docs/manifest.md`, `docs/onboarding.md`, ten plik,
  `CLAUDE.md`): opisują *stan obecny* projektu, zawsze zgodny z kodem.
  Zmieniasz architekturę, warstwy, endpointy albo sposób uruchamiania?
  Zaktualizuj `docs/manifest.md` i `docs/onboarding.md` w tym samym commicie.
  Nie duplikuj treści między dokumentami — README linkuje do `docs/`, nie
  kopiuje. Rzeczy planowane opisuj jednoznacznie jako planowane.
- **`docs/specs/*.md`** — efemeryczne briefy specyfikujące implementację
  jednej funkcjonalności (np. wizja nowego mechanizmu, przewodnik po dodaniu
  konkretnego typu rozszerzenia). Żyją tylko na czas zadania, które opisują.
  **Po zakończeniu implementacji, w tym samym commicie**: przenieś trwałą
  treść (fakty o strukturze, decyzje „dlaczego") do `docs/manifest.md`/
  `docs/onboarding.md`, usuń plik z `docs/specs/`. Historia gita jest
  archiwum — nie trzymaj nieaktualnych specyfikacji „na wszelki wypadek".
  README nigdy nie linkuje do `docs/specs/`.

## Koniec sesji
1. `git status`
2. Commit z krótkim, konkretnym opisem.
3. Pytaj o zgodę przed `git push origin master`.