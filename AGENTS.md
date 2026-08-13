# Instrukcje dla Agenta AI (System Regis)

## 1. Start Sesji (Pierwsze zapoznanie)
Podczas pierwszego zapoznania się z projektem koniecznie przeczytaj dokumenty w katalogu `docs/`:
- `docs/manifest.md`
- `docs/onboarding.md`

## 2. Obowiązek Stosowania Chain of Thought (COT)
Przed przystąpieniem do jakichkolwiek modyfikacji kodu, edycji planów, tworzenia nowych plików czy wykonywania złożonych komend, agent **ma obowiązek przeprowadzić proces przemyślanego planowania i analizy (Chain of Thought)**.

Agent stosuje analizę COT w sposób naturalny i elastyczny, dostosowując głębokość i formę przemyśleń do skali oraz skomplikowania zadania – **bez konieczności sztywnego i szablonowego wypisywania ponumerowanych punktów przed każdą odpowiedzią**.

Kluczowe filary analizy, o których agent musi pamiętać:
- **Zrozumienie celu (Goal Understanding)**: Przeanalizowanie intencji użytkownika oraz kontekstu w projekcie, by rozwiązać właściwy problem, a nie tylko jego powierzchniowe objawy.
- **Krytyczne myślenie i weryfikacja sugestii (Critical Thinking)**: Samodzielne sprawdzanie faktów i technicznego sensu proponowanych rozwiązań. Jeśli pomysł zawiera luki lub istnieje lepsza alternatywa – wykaż to przed realizacją.
- **Sprawdzenie faktów (Fact Checking)**: Weryfikacja rzeczywistego stanu kodu, ścieżek plików, nazw funkcji i schematów danych przed ich użyciem (nie zgaduj).
- **Plan działania i przemyślenie skutków (Action Plan & Consequences)**: Przemyślenie kroków koniecznych do zrealizowania zadania, skutków ubocznych oraz przypadków brzegowych.


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
