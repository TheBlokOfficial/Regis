# Model dynamicznego kontekstu agenta — wizja docelowa

> **Status**: To jest dokument wizji, wypracowany w rozmowie projektowej — **nie**
> opis dzisiejszego kodu. Zastępuje część założeń z obecnego `docs/manifest.md`
> (sekcje o `SmartHomeAddon`, `Device`, `DeviceRegistry`).
>
> Z trzech dokumentów przygotowanych wcześniej w tej samej sesji:
> - **`adding-integrations.md` jest wycofany** — opisuje kontrakt `DeviceIntegration`
>   i mechanizm `_resolve` po nazwie, oba zastąpione w tej wizji.
> - **Dopisek bezpieczeństwa do `manifest.md` oraz `frontend.md` pozostają
>   aktualne bez zmian** — dotyczą innych warstw systemu, których ta wizja nie dotyka.
>
> **Rewizja po pierwszym wdrożeniu**: sekcje 2 (Dostawca kontekstu), 3, i nowa
> 4.5 zostały zaktualizowane w kolejnej sesji projektowej, **po** tym, jak
> pierwsza wersja tej wizji została już zaimplementowana (patrz commit
> `b55bbb0` + poprawki `bec9d21`). Kod na moment tej rewizji **jeszcze nie**
> odzwierciedla poniższych zmian dot. Faktów — to świeży dług do spłacenia,
> nie opis stanu obecnego.

---

## 1. Zasada nadrzędna

Każda warstwa zna wyłącznie **kształt** tego, co dostaje od warstwy pod spodem —
nigdy **treść** ani **pochodzenie**. Wszystkie decyzje poniżej są tej jednej
zasady konsekwencją, nie osobnymi wyborami.

---

## 2. Role systemu

### Agent (Kernel)
Odbiorca. Nie zna żadnego pluginu, integracji, ani domeny. Dostaje co turę
trzy płaskie kanały treści (sekcja 3) i nic więcej.

### Gateway (Agregator)
Jedyny punkt zbierający wszystko, i to od **Pluginów**, nigdy bezpośrednio
od pojedynczych integracji wewnątrz nich. Budowany od zera przy każdej turze
agenta, w jednym przebiegu. Nadaje encjom opaque identyfikatory (sekcja 4.2).
Nie interpretuje treści niczego, co dostaje.

### Kontrakt (Specyfikacja)
Czysta deklaracja kształtu — czasownika (parametry narzędzia) i rzeczownika
(pola encji). Zero logiki, zero stanu.

### Plugin
Jedyna jednostka, z którą rozmawia Gateway. Implementuje jeden lub więcej
Kontraktów i zwraca Gateway już w pełni gotowy wkład na tę turę: narzędzia,
encje (z rozwiązanymi grupami, sekcja 4.4) **i opcjonalnie fakty** (sekcja 4.5)
— wszystkie trzy z tej samej, jednej metody budującej. Fakty nie mają
osobnego dostawcy — są zwyczajnym, dodatkowym wkładem Pluginu, dokładnie tak
samo jak narzędzia i encje.

### Integracja (szczegół wewnętrzny Pluginu)
Rozmawia z jednym, konkretnym systemem zewnętrznym. Nigdy nie jest widoczna
dla Gateway ani Agenta bezpośrednio.

~~### Dostawca kontekstu~~
**Usunięte jako osobna rola** (rewizja, patrz sekcja 4.5). Wcześniejsza wersja
tej wizji traktowała Fakty jako produkt osobnej kategorii uczestników,
równoległej do Pluginów. Okazało się to niepotrzebnym rozdwojeniem: skoro
każdy Fakt musi mieć bliźniacze narzędzie dostarczające tę samą informację
na żądanie (sekcja 4.5), to coś, co "dostarcza fakt", z definicji już jest
czymś, co dostarcza narzędzie — czyli Pluginem. Przykład z poprzedniej wersji
(dostawca daty/godziny) staje się zwyczajnym, minimalnym Pluginem z jednym
narzędziem (`get_time`) i jednym odpowiadającym mu Faktem.

---

## 3. Trzy kanały treści agenta

| Kanał | Co zawiera | Kto buduje |
|---|---|---|
| **Narzędzia** | Schematy wywołań (nazwa, opis, parametry) | Pluginy, przez Kontrakt |
| **Encje** | Lista rzeczy do interakcji, z adresowalnym opaque ID i etykietami możliwości | Pluginy |
| **Fakty** | Kontekst do zrozumienia, nigdy do adresowania — zawsze z bliźniaczym narzędziem (sekcja 4.5) | Pluginy, opcjonalnie |

Fakty pozostają **osobną, nietechniczną sekcją tekstu** w kontekście agenta —
nie są wplatane w tę samą listę co Encje, mimo że obie mogą dziś pochodzić
od tego samego Pluginu. Rozdział jest strukturalny, nie stylistyczny: patrz
test w sekcji 4.5.

---

## 4. Kluczowe mechanizmy

### 4.1 Granularność możliwości i logika częściowego dopasowania
Etykieta na encji opisuje możliwości **w obrębie** narzędzia, nie płaskie
tak/nie na poziomie całego narzędzia. Logika częściowego dopasowania
mieszka wewnątrz wykonania, po stronie Integracji, orkiestrowanej przez Plugin.

### 4.2 Adresowanie encji — opaque ID, stabilne bez pamiętania
Agent adresuje encje po identyfikatorze nadanym przez Gateway — deterministyczna
pochodna (nieprzezroczysty skrót) z (tożsamość Pluginu + wewnętrzne odniesienie),
liczona od nowa co turę, bez trzymania żadnej pamiętanej między turami tabeli.

### 4.3 Satelita → pokój: dwuetapowa rejestracja
Rdzeń zna wyłącznie opaque ID satelity. Mapowanie ID → pokój jest prywatną
wiedzą pluginu Smart Home.

### 4.4 Grupy jako w pełni wewnętrzna sprawa Pluginu
Grupa jest z zewnątrz nieodróżnialna od pojedynczej encji — Plugin oddaje ją
Gateway już w pełni rozwiązaną. Gateway pozostaje w pełni jednoprzebiegowy.

### 4.5 Fakty muszą mieć bliźniacze narzędzie — i test rozróżnienia Encja vs Fakt

**Zasada symetrii**: każda informacja proaktywnie podana jako Fakt musi być
**również** dostępna reaktywnie, przez narzędzie zwracające dokładnie tę samą
treść. Fakt jest wyłącznie optymalizacją (oszczędź agentowi wywołania, jeśli
logika budująca kontekst uzna informację za prawdopodobnie przydatną teraz)
— nigdy jedynym kanałem dostępu. Bez tej zasady agent "uderza w mur": jeśli
coś istnieje wyłącznie jako Fakt i akurat nie zostało w danej turze pokazane
(bo np. filtr uznał to za nieistotne), agent nie ma żadnego sposobu, żeby o
to zapytać ponownie.

Konsekwencja praktyczna: to, co wcześniej uzasadniało usunięcie `list_devices`
("kanał Encji zawsze kompletny, narzędzie redundantne") przestaje obowiązywać
w tej samej, bezwzględnej formie, jeśli Plugin zacznie **filtrować** (nie
tylko sortować) Encje po kontekście przestrzennym — patrz zasada symetrii:
jeśli coś zostaje realnie schowane, musi istnieć narzędzie-fallback, które to
odsłania na żądanie. Jeśli Plugin wyłącznie **sortuje/priorytetyzuje**
(pełna lista zawsze obecna, tylko kolejność się zmienia), fallback nie jest
potrzebny — kompletność jest zachowana inaczej niż literalnie, ale zachowana.
Wybór między tymi dwoma trybami filtrowania jest decyzją konkretnego Pluginu,
nie architektury — architektura wymaga tylko: **jeśli chowasz, musisz też
dawać sposób na odkrycie tego, co schowałeś.**

**Test rozróżnienia Encja vs Fakt** (bo to samo słowo — np. "Salon" — może
występować w obu rolach naraz, bez sprzeczności): **X jest Encją wtedy i
tylko wtedy, gdy przekazanie X jako celu narzędzia powoduje, że Gateway
znajduje w swojej tabeli routingu, dokąd to wywołanie skierować.** Wszystko
inne jest co najwyżej Faktem, niezależnie jak bardzo "ma tożsamość"
pojęciowo. Przykład: "jesteś w Salonie" (wartość do zrozumienia, nigdy cel
wywołania) to Fakt; "Salon" jako skonfigurowana grupa lampek, na której
działa `turn_on`, to Encja. To dwie osobne, niezależne informacje o tym
samym miejscu w świecie — Plugin może mieć jedną bez drugiej.

**Naturalna okazja, nie mechanizm specjalny**: Plugin, budując Encje na tę
turę, może przeczytać własny Fakt (np. o obecnej lokalizacji) i na tej
podstawie posortować/oznaczyć powiązane Encje jako priorytetowe — to zwykłe
czytanie danych przez Plugin, nie wymaga niczego po stronie Gateway ani
Kontraktu.

---

## 5. Miejsce pojęć domenowych

"Encja" jako generyczny kształt żyje w Kontrakcie. Konkretna jej realizacja
jest pojęciem konkretnego Pluginu, nie rdzenia.

---

## 6. Świadomie zaakceptowane kompromisy

- **Miękkie sprzężenie nazewnicze** między Faktem o pochodzeniu (satelita) a
  Pluginem interpretującym jego ID — oparte na konwencji, nie formalnym kontrakcie.
- **Symetria Fakt↔narzędzie (sekcja 4.5) jest dyscypliną autora Pluginu, nie
  wymuszaną przez Gateway.** Wymuszenie tego mechanicznie wymagałoby, żeby
  Gateway rozumiał treść (dopasował klucz Faktu do nazwy narzędzia), co
  złamałoby jego ślepotę — tej samej natury kompromis co punkt wyżej.
- **Spójność słownika między integracjami wewnątrz jednego Pluginu** nie jest
  wymuszona przez architekturę — odpowiedzialność autora Pluginu.
- **Dwuetapowa rejestracja** (sekcja 4.3).

---

## 7. Co zostaje bez zmian względem dzisiejszego systemu

Warstwowość i jednokierunkowa zależność, świeże budowanie kontekstu przy
każdej turze, konfiguracja w plikach JSON, filozofia jawnej rejestracji
zamiast dynamicznego ładowania pluginów (YAGNI).

## 8. Co znika lub zmienia rolę względem dzisiejszego (już zaimplementowanego) kodu

- **`ContextProvider` jako osobny kontrakt i `context_providers/` jako osobny
  katalog** — znika (sekcja 2). Fakty stają się opcjonalnym polem
  `PluginContribution`, produkowanym przez zwykłe Pluginy. `DateTimeContextProvider`
  staje się minimalnym Pluginem z jednym narzędziem (`get_time`) i
  odpowiadającym mu Faktem — dowód zasady symetrii, nie osobny byt.
- **Addon jako właściciel modelu i logiki** — znika, zastąpiony przez Plugin.
- **Dopasowywanie po nazwie** (`_resolve`) — znika, zastąpione opaque ID.
- **Kompozytor jako osobna, Gateway-poziomowa kategoria** — nie istnieje w
  tej wizji; Gateway pozostaje w pełni jednoprzebiegowy (sekcja 4.4).

---

## 9. Poza zakresem — świadomie odłożone

- **Grupy międzypluginowe** (scena łącząca światło i muzykę z dwóch różnych
  pluginów) — wymagałoby Gateway-poziomowego mechanizmu kompozycji, którego
  ta wizja świadomie unika.
- **Automatyzacje/skrypty** (sekwencja **różnych** czasowników, np. "wychodzę"
  = zgaś światła + zablokuj drzwi) — odrębne pojęcie od grupy.

---

## 10. Status otwartych punktów

**Rozbieżność wizja↔kod do zaadresowania w kolejnym kroku implementacyjnym**:
sekcje 2, 3 i 4.5 (Fakty jako pole `PluginContribution`, usunięcie osobnego
`ContextProvider`/`context_providers/`) nie są jeszcze odzwierciedlone w
zaimplementowanym kodzie — ten sam dokument w chwili pierwszego wdrożenia
(commit `b55bbb0`) opisywał wciąż osobną rolę Dostawcy kontekstu. Wymaga
osobnego promptu naprawczego, analogicznego do poprzedniej rundy poprawek.

Jedyny pozostały czysto implementacyjny detal (niearchitektoniczny): wybór
konkretnej funkcji skrótu do opaque ID (sekcja 4.2).
