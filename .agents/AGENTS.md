# Regis Workspace Rules

- **KRYTYCZNE:** Model pracujący w tym projekcie nie może wprowadzać ŻADNYCH zmian w kodzie, chyba że użytkownik wyraźnie i jednoznacznie mu to nakaże.
- **Unikaj nadmiernego używania emotikon (ikonek) w interfejsie CLI i logach.**
- Używaj ich tylko tam, gdzie są niezbędne do kierowania wzrokiem lub faktycznie poprawiają czytelność (np. krzyżyk oznaczający wyjście/błąd, ptaszek oznaczający sukces). Dodawanie ikon do absolutnie każdej opcji menu wygląda nieprofesjonalnie. Interfejs Regis ma docelowo pozostać stonowany i ascetyczny.

## Zalecenia dotyczące UX (CLI)
Poniższe wytyczne stanowią zbiór dobrych praktyk wypracowanych podczas refaktoryzacji interfejsu (są to luźne propozycje na przyszłość pomagające utrzymać spójność, a nie sztywne reguły):
- **Minimalizm barwny**: Preferuj użycie czystej bieli (`[bold white]`) dla nagłówków czy ważnych tekstów i szarości (`[dim]`) dla elementów "tła" (logi, instrukcje pomocnicze, długie dumpy JSON).
- **Kolory celowe**: Staraj się unikać jaskrawych barw (np. `cyan`, `yellow`), jeśli pełnią funkcje wyłącznie estetyczne. Rezerwuj wyraziste kolory (np. `[red]`, `[green]`) do informowania o istotnych zdarzeniach (błędy, sukcesy).
- **Lżejsza struktura**: Zamiast otaczać bloki tekstu masywnymi panelami z obramowaniami (`Panel`), używaj pogrubionych tytułów oddzielonych delikatnymi liniami poziomymi (`Rule(style="dim")`).
- **Niestandardowe motywy w promptach**: Przy korzystaniu z bibliotek wyboru (np. `questionary`) warto aplikować własny, wyciszony motyw stylów (np. stosując `fg:ansigray`), aby pozbyć się "krzykliwych", domyślnych niebieskich lub żółtych highlightów.

## Protokoły Pracy Agenta (Regis)

**[PROCEDURA STARTOWA - OBOWIĄZKOWA]**
Zanim rozpoczniesz realizację pierwszego polecenia użytkownika w nowej sesji, MASZ OBOWIĄZEK w pierwszej kolejności użyć narzędzi do czytania plików w tle, aby zapoznać się z plikami w następującej kolejności:
1. **`docs/MANIFEST.md`** — NAJWAŻNIEJSZY PLIK. Definiuje filozofię, cele i rozstrzygnięte decyzje projektowe. Twoje decyzje MUSZĄ być z nim zgodne.
2. **`docs/AGENT_GUIDE.md`** — Przewodnik po tym jak pracować w tym projekcie. Zawiera listę decyzji do nie ruszania i typowych błędów agentów.
3. **`.agents/HANDOFF.md`** — Stan projektu po ostatniej sesji.
4. **`.agents/TASKS.md`** — Lista aktywnych zadań.
Nie pytaj użytkownika o pozwolenie na przeczytanie tych plików, po prostu zrób to cicho w tle.

**[PROCEDURA ZAMYKANIA SESJI]**
Kiedy użytkownik zasygnalizuje koniec pracy (hasła: "na dziś to wszystko", "kończymy", "zamykamy sesję", "koniec" itp.), obowiązuje Cię ZAKAZ zwykłego pożegnania się. Zamiast tego musisz natychmiast wykonać następującą sekwencję zadań:
1. **Zastąp zawartość `.agents/HANDOFF.md` nową treścią**: HANDOFF.md nie jest dziennikiem historycznym — jest zawsze aktualnym stanem projektu. Napisz NOWĄ wersję całego pliku (nie dopisuj na końcu). Zawrzyj: co zostało zrobione w tej sesji, aktualny stan kodu i precyzyjne kroki startowe dla następnego agenta. Stara wersja jest zachowana w historii git.
2. **Zaktualizuj plik `.agents/TASKS.md`**: Odznacz zrealizowane zadania lub zaktualizuj ich status. Nigdy nie usuwaj zadań samodzielnie — tylko archiwizuj na polecenie użytkownika.
3. **Zapisz zmiany w repozytorium**: Użyj narzędzia `run_command` w głównym katalogu projektu, aby odpalić kolejno: `git add . ; git commit -m "Auto-zapis sesji agenta: [podsumowanie]" ; git push`. (używaj średników w PowerShell, nie &&)
Dopiero po pomyślnym wykonaniu tych kroków, poinformuj użytkownika wylistowując co dokładnie zaktualizowałeś, potwierdź wysłanie do repozytorium i pożegnaj się.

**[FILOZOFIA I ARCHITEKTURA PROJEKTU]**
Bezwzględnie zapoznaj się z plikiem `docs/MANIFEST.md` (najwyższy autorytet) oraz `docs/AGENT_GUIDE.md` (praktyczne wytyczne dla agentów). Te dokumenty muszą przyświecać każdej Twojej decyzji programistycznej. Plik `docs/ARCHITECTURE.md` jest starszym dokumentem — w przypadku sprzeczności, `MANIFEST.md` ma pierwszeństwo.
