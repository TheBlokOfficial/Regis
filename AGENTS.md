# AGENTS.md — System Regis

## Kontekst
Architektura/decyzje projektowe: `docs/manifest.md`, `docs/onboarding.md`.
Czytaj na żądanie, gdy zadanie tego wymaga — nie zakładaj z góry, że trzeba
je wczytać przy każdej zmianie.

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
