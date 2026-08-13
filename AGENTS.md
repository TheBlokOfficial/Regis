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

## Jakość kodu
SOLID, DRY, KISS, YAGNI, Boy Scout Rule.

## Koniec sesji
1. `git status`
2. Commit z krótkim, konkretnym opisem.
3. Pytaj o zgodę przed `git push origin master`.
