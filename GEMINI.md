# Instrukcje dla Agenta AI (Regis)

## 1. Start Sesji (Pierwsze zapoznanie)
Podczas pierwszego zapoznania się z projektem koniecznie przeczytaj dokumenty w katalogu `docs/`:
- `docs/manifest.md`
- `docs/onboarding.md`

## 2. Obowiązkowa Analiza i Planowanie (Chain of Thought)
Przed przystąpieniem do jakichkolwiek modyfikacji kodu, tworzenia plików czy wykonywania złożonych komend, agent **bezwzględnie musi** przeprowadzić proces przemyślanego planowania i analizy:
1. **Zrozumienie celu**: Przeanalizuj intencję użytkownika oraz kontekst w projekcie. Zidentyfikuj problem, a nie tylko jego objawy.
2. **Krytyczne myślenie i weryfikacja sugestii**: Nie traktuj sugestii ani propozycji użytkownika jak bezwzględnej wyroczni. Zweryfikuj fakty samodzielnie, sprawdź techniczny sens oraz jakość proponowanego rozwiązania. Jeśli pomysł użytkownika zawiera błędy, luki architektoniczne lub istnieje obiektywnie lepsze rozwiązanie – przeanalizuj to krytycznie i zwróć na to uwagę przed ślepą realizacją.
3. **Sprawdzenie faktów (Nie zgaduj)**: Zawsze zweryfikuj rzeczywisty stan kodu, ścieżki plików, nazwy funkcji i schematy danych przed ich użyciem.
4. **Plan działania i przemyślenie skutków**: Określ kroki konieczne do zrealizowania zadania oraz rozważ potencjalne skutki uboczne, przypadki brzegowe i wpływ na inne moduły.
5. **Dopiero po przeanalizowaniu**: Przejdź do wykonania konkretnych edycji i generowania kodu.

## 3. Standardy Jakości Kodu i Dobre Praktyki
Pisz kod czysty, modułowy i łatwy w utrzymaniu. Każda zmiana w kodzie musi spełniać poniższe zasady:
- **SOLID**: 
  - *Single Responsibility*: Klasa/moduł/funkcja ma tylko jedną odpowiedzialność.
  - *Open/Closed*: Kod otwarty na rozbudowę, zamknięty na modyfikacje.
  - *Liskov Substitution*: Podklasy mogą zastępować klasy bazowe bez zaburzania działania programu.
  - *Interface Segregation*: Twórz małe, dedykowane interfejsy zamiast ogólnych i przeładowanych.
  - *Dependency Inversion*: Polegaj na abstrakcjach, a nie na konkretnych implementacjach.
- **DRY (Don't Repeat Yourself)**: Unikaj duplikowania logiki – wydzielaj powtarzalne fragmenty do skomponowanych funkcji lub modułów.
- **KISS (Keep It Simple, Stupid)**: Wybieraj najprostsze działające rozwiązanie. Unikaj nadmiernej inżynierii (over-engineering).
- **YAGNI (You Aren't Gonna Need It)**: Implementuj wyłącznie to, co jest aktualnie wymagane. Nie pisz kodu "na zapas".
- **Rule of Least Surprise (POLA)**: Kod powinien zachowywać się w sposób intuicyjny i przewidywalny dla innych programistów.
- **Boy Scout Rule**: Zostaw kod w stanie lepszym, niż go zastałeś (poprawiaj drobne usterki, czytelność i typowanie przy okazji prac w danym miejscu).

## 4. Koniec Sesji (Procedura zapisu)
Gdy użytkownik zasygnalizuje koniec sesji (np. *"kończymy sesję"*, *"na dzisiaj starczy"*):
1. Sprawdź zmodyfikowane pliki (`git status`).
2. Wykonaj commit z czytelnym i zwięzłym opisem zmian.
3. Wykonaj `git push` do repozytorium GitHub (`origin master`).
