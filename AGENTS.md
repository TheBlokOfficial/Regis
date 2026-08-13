# Instrukcje dla Agenta AI (System Regis)

Ten plik obowiązuje każdego agenta AI pracującego w repozytorium (Claude Code
i inne narzędzia zgodne z konwencją AGENTS.md). Instrukcje specyficzne dla
Claude Code są w `CLAUDE.md`, który importuje ten plik.

## 1. Kontekst projektu
Kluczowa dokumentacja projektu: `docs/manifest.md`, `docs/onboarding.md`.
(W Claude Code te pliki są importowane automatycznie przez `CLAUDE.md` —
patrz ten plik — więc ładują się w każdej sesji bez konieczności pamiętania
o tym przez agenta.)

## 2. Zanim zaczniesz kodować
- **Nie zgaduj.** Zweryfikuj rzeczywisty stan kodu — ścieżki plików, nazwy
  funkcji, schematy danych — zanim ich użyjesz.
- **Duże/niejasne zmiany:** najpierw eksploruj i zaplanuj, dopiero potem
  implementuj. W Claude Code użyj do tego trybu plan mode.
- **Małe, jednoznaczne poprawki** (literówka, log, rename zmiennej) —
  działaj od razu, bez narzutu planowania.
- **Zawsze miej sposób weryfikacji** swojej pracy (test, build, lint) i
  uruchom go po zmianie — nie zakładaj, że "wygląda na gotowe".
- Przemyśl skutki uboczne i przypadki brzegowe, nie tylko happy path.
- Jeśli sugerowane rozwiązanie ma luki lub istnieje lepsza alternatywa —
  zgłoś to zamiast realizować bezrefleksyjnie.

## 3. Standardy jakości kodu
Każda zmiana powinna być zgodna z:
- **SOLID** (Single Responsibility, Open/Closed, Liskov Substitution,
  Interface Segregation, Dependency Inversion)
- **DRY** — nie duplikuj logiki
- **KISS** — najprostsze działające rozwiązanie, bez nadmiernej inżynierii
- **YAGNI** — implementuj tylko to, co aktualnie wymagane
- **POLA (Rule of Least Surprise)** — kod ma zachowywać się intuicyjnie
- **Boy Scout Rule** — zostaw kod czystszy niż go zastałeś, przy okazji
  pracy w danym miejscu

## 4. Koniec sesji
Gdy użytkownik zasygnalizuje koniec sesji (np. "kończymy sesję", "na dziś
starczy"):
1. Sprawdź `git status`.
2. Wykonaj commit z czytelnym, zwięzłym opisem zmian.
3. **Zapytaj o potwierdzenie przed `git push origin master`.** Nie pushuj
   automatycznie bez wyraźnej zgody, chyba że w danej sesji ustalono inaczej.

> Instrukcja w punkcie 3 jest kontekstem dla agenta, nie twardą blokadą —
> jeśli push na `master` bez potwierdzenia ma być fizycznie niemożliwy,
> potrzebny jest hook (`PreToolUse` na `git push`), nie zapis w tym pliku.
