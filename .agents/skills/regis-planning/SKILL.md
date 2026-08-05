---
name: regis-planning
description: Aktywuj ten skill za każdym razem gdy tworzysz lub aktualizujesz artefakty planowania: implementation_plan.md lub task.md. Zawiera zasady pisania planów i list zadań w projekcie Regis.
---

# Skill: Planowanie w Projekcie Regis

Ten skill definiuje zasady tworzenia artefaktów planowania. Przeczytaj go w całości przed napisaniem `implementation_plan.md` lub `task.md`.

---

## Część 1 — `implementation_plan.md`

### Cel artefaktu

`implementation_plan.md` to dokument do zatwierdzenia przez użytkownika. Po jego przeczytaniu użytkownik musi rozumieć **co** zostanie zmienione, **dlaczego** i **w jaki sposób** — bez potrzeby zaglądania do historii rozmowy.

### Zasady pisania

**Zasada: Pisz dla nieznanego agenta, nie dla siebie.**
Wykonujący agent nie ma dostępu do tej rozmowy. Każda decyzja projektowa, która nie jest oczywista, musi być wyjaśniona inline. Nie zakładaj kontekstu.

**Zasada: Grupuj zmiany po komponentach, nie po plikach.**
Pliki to szczegół implementacyjny. Najpierw opisz co zmienia się w komponencie (np. `llm`, `audio`, `satellite`, `controller`), a dopiero potem wylistuj konkretne pliki. To pozwala użytkownikowi ocenić zakres bez czytania każdej linii.

**Zasada: Pytania otwarte to blokery — zaznacz je wyraźnie.**
Jeśli istnieje decyzja projektowa, której jeszcze nie podjęto, a od której zależy implementacja — wpisz ją do sekcji `## Open Questions` z alertem `[!IMPORTANT]` lub `[!CAUTION]`. Nie planuj "na ślepo" wokół nierozstrzygniętej kwestii.

**Zasada: Sekcja weryfikacji jest obowiązkowa.**
Każdy plan musi zawierać `## Verification Plan` z konkretną listą: co uruchomić, co sprawdzić ręcznie, co potwierdzić z użytkownikiem. Ogólne sformułowania ("sprawdzić czy działa") są niedopuszczalne.

**Zasada: Nie opisuj tego, co się nie zmienia.**
Plan obejmuje wyłącznie zmiany. Nie wyjaśniaj jak działa istniejący kod, chyba że jest to niezbędne do uzasadnienia decyzji.

### Obowiązkowa struktura

```markdown
# [Zwięzły tytuł opisujący cel zmiany]

Jedno lub dwa zdania: jaki problem rozwiązuje ta zmiana i dlaczego teraz.

## Open Questions
(pomiń jeśli nie ma nierozstrzygniętych kwestii)

## Proposed Changes

### [Nazwa Komponentu]
Co się zmienia i dlaczego.

#### [MODIFY] [nazwa pliku](file:///.../ścieżka)
#### [NEW] [nazwa pliku](file:///.../ścieżka)
#### [DELETE] [nazwa pliku](file:///.../ścieżka)

## Verification Plan

### Automated Tests
### Manual Verification
```

---

## Część 2 — `task.md`

### Cel artefaktu

`task.md` to lista zadań do wykonania przez agenta. Jest żywym dokumentem — aktualizuj go w trakcie pracy, nie tylko na początku i końcu. Jego jakość bezpośrednio wpływa na to, czy agent wykona zadanie poprawnie bez dodatkowych pytań.

### Zasady pisania

**Zasada: Każde zadanie musi być atomowe.**
Zadanie jest atomowe jeśli można je wykonać i niezależnie zweryfikować bez kontekstu pozostałych zadań. Jeśli zadanie wymaga wiedzy o innym zadaniu żeby uznać je za skończone — podziel je lub połącz.

**Zasada: Każde zadanie musi zawierać kontekst "dlaczego".**
W nawiasach kursywą lub w podpunkcie dodaj uzasadnienie. Nie pisz "Usuń parsowanie argparse" — napisz "Usuń parsowanie argparse z `__main__.py` *(konfiguracja pochodzi teraz z obiektu `SatelliteConfig`, a nie z CLI)*".

**Zasada: Każde zadanie musi mieć jawne kryterium "done".**
Co konkretnie sprawdzić, żeby uznać zadanie za skończone? Może to być: plik istnieje i przechodzi import, test przechodzi, endpoint odpowiada, log zawiera określony komunikat. Jeśli nie możesz sformułować kryterium — zadanie jest za niejasne i wymaga podziału.

**Zasada: Zależności między zadaniami muszą być jawne.**
Jeśli zadanie B nie może być wykonane przed A — napisz to. Użyj wcięcia lub adnotacji `*(wymaga: zadanie X)*`. Nie zakładaj że kolejność na liście jest oczywista.

**Zasada: Nierozstrzygnięte decyzje to nie zadania.**
Jeśli podczas tworzenia `task.md` odkryjesz, że jakieś zadanie wymaga decyzji projektowej, której jeszcze nie podjęto — nie wpisuj go jako zadania. Cofnij się do `implementation_plan.md` i dodaj je do `Open Questions`. Poinformuj użytkownika.

**Zasada: Aktualizuj `task.md` synchronicznie z pracą — nigdy na końcu.**
Przed rozpoczęciem każdego zadania oznacz je jako `[/]` w `task.md`. Bezpośrednio po ukończeniu oznacz jako `[x]`. Nie odkładaj aktualizacji do końca bloku pracy. `task.md` musi w każdej chwili odzwierciedlać rzeczywisty stan — nie jest podsumowaniem które piszesz po fakcie.

### Format zadania

```markdown
- [ ] **Krótki tytuł zadania** — [komponent/plik]
  - *Dlaczego*: uzasadnienie jednym zdaniem
  - *Co zmienić*: konkretny opis akcji (plik, funkcja, interfejs)
  - *Done gdy*: mierzalne kryterium ukończenia
  - *(wymaga: #N)* — jeśli dotyczy
```

### Obowiązkowa struktura `task.md`

```markdown
# Task: [Tytuł z implementation_plan.md]

> Odniesienie: [implementation_plan.md](file:///ścieżka/do/pliku)

## Zadania

- [ ] **...** — [komponent]
  - *Dlaczego*: ...
  - *Co zmienić*: ...
  - *Done gdy*: ...

## Zablokowane / Do wyjaśnienia
(zadania wstrzymane z powodu nierozstrzygniętych decyzji)
```

---

## Część 3 — Relacja między artefaktami

`implementation_plan.md` → zatwierdza użytkownik → `task.md` → wykonuje agent.

Każde zadanie w `task.md` musi dać się jednoznacznie przypisać do sekcji w `implementation_plan.md`. Jeśli nie możesz tego zrobić — albo zadanie jest spoza zakresu planu (wróć do użytkownika), albo plan jest niekompletny (zaktualizuj go).

Aktualizując `task.md` w trakcie pracy, nigdy nie usuwaj zadań — używaj statusów:
- `[ ]` — do zrobienia
- `[/]` — w toku
- `[x]` — ukończone
- `[-]` — anulowane z adnotacją dlaczego
