# Model dynamicznego kontekstu agenta — wizja docelowa

> **Status**: To jest dokument wizji, wypracowany w rozmowie projektowej — **nie**
> opis dzisiejszego kodu. Zastępuje część założeń z obecnego `docs/manifest.md`
> (sekcje o `SmartHomeAddon`, `Device`, `DeviceRegistry`).
>
> Z trzech dokumentów przygotowanych wcześniej w tej samej sesji:
> - **`adding-integrations.md` jest wycofany** — opisuje kontrakt `DeviceIntegration`
>   i mechanizm `_resolve` po nazwie, oba zastąpione w tej wizji. Do napisania od
>   nowa dopiero po realnym wdrożeniu tego modelu w kodzie, nie spekulacyjnie teraz.
> - **Dopisek bezpieczeństwa do `manifest.md` oraz `frontend.md` pozostają
>   aktualne bez zmian** — dotyczą innych warstw systemu (postawa sieciowa,
>   konwencje Web UI), których ta wizja nie dotyka.
>
> Dokument celowo nie zawiera sygnatur kodu ani nazw klas — to specyfikacja
> koncepcyjna, punkt wyjścia do konkretnego planu cięcia i przepisania.

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
agenta, w **jednym przebiegu** — pyta każdy zarejestrowany Plugin i każdego
Dostawcę kontekstu o jego wkład, skleja w trzy płaskie listy, rozstrzyga
kolizje nazw. Nadaje encjom opaque identyfikatory (sekcja 4.2). Nie
interpretuje treści niczego, co dostaje.

### Kontrakt (Specyfikacja)
Czysta deklaracja kształtu — czasownika (parametry narzędzia) i rzeczownika
(pola encji). Zero logiki, zero stanu, nigdy nie istnieje jako uruchomiony
obiekt. Pozwala niezależnym Pluginom tej samej domeny realizować ten sam
interfejs bez znajomości siebie nawzajem.

### Plugin
**Jedyna jednostka, z którą rozmawia Gateway.** Implementuje jeden lub więcej
Kontraktów i zwraca Gateway już w pełni gotową, spłaszczoną listę swoich
narzędzi i encji — łącznie z rozwiązanymi grupami (sekcja 4.4). To, ile ma
wewnątrz integracji, jak je koordynuje i jak łączy ich urządzenia w grupy,
jest w całości jego prywatną sprawą.

### Integracja (szczegół wewnętrzny Pluginu)
Rozmawia z jednym, konkretnym systemem zewnętrznym (np. Home Assistant).
Nigdy nie jest widoczna dla Gateway ani Agenta bezpośrednio — Plugin ją
orkiestruje. To tutaj mieszka logika dopasowania żądania do realnych
możliwości konkretnej encji (sekcja 4.1).

### Dostawca kontekstu
Równoległa kategoria — nie dostarcza narzędzi ani encji, tylko fakty o
świecie i o pochodzeniu requestu (godzina, pogoda, opaque ID satelity).
Zawsze domenowo pusty.

---

## 3. Trzy kanały treści agenta

| Kanał | Co zawiera | Kto buduje |
|---|---|---|
| **Narzędzia** | Schematy wywołań (nazwa, opis, parametry) | Pluginy, przez Kontrakt |
| **Encje** | Lista rzeczy do interakcji, z etykietami możliwości, w tym już rozwiązane grupy | Pluginy |
| **Fakty** | Kontekst niezwiązany z żadnym narzędziem (czas, pogoda, ID pochodzenia requestu) | Dostawcy kontekstu |

Fakty trafiają także w dół, do Pluginów budujących swoje encje na tę turę —
Plugin może użyć rozpoznanego faktu do decyzji co pokazać jako priorytet.

---

## 4. Kluczowe mechanizmy

### 4.1 Granularność możliwości i logika częściowego dopasowania
Etykieta na encji opisuje możliwości **w obrębie** narzędzia (np. `set_light`:
`state`, `brightness`, bez `rgb`), nie płaskie tak/nie na poziomie całego
narzędzia. Logika "zastosuj to, co ma sens, zgłoś uczciwie co pominięto"
mieszka wewnątrz wykonania, po stronie Integracji, orkiestrowanej przez
Plugin.

### 4.2 Adresowanie encji — opaque ID, stabilne bez pamiętania
Agent adresuje encje po identyfikatorze nadanym przez Gateway, nigdy po
natywnym ID zewnętrznego API (to zdradzałoby integrację stojącą za encją).

**Rozstrzygnięcie stabilności między turami**: opaque ID jest **deterministyczną
pochodną** stabilnych danych wejściowych (tożsamość Pluginu + wewnętrzne
odniesienie, które ten Plugin sam sobie nadaje) — nie wpisem w pamiętanej
między turami tabeli. Ta sama encja zawsze daje ten sam opaque ID, bo
funkcja wyliczająca jest ta sama, a wejścia się nie zmieniają — więc Gateway
może **nadal budować wszystko od zera co turę**, zgodnie z zasadą nadrzędną,
i identyfikator mimo to pozostaje stabilny w historii rozmowy. Pochodna musi
być nieprzezroczysta (np. skrót kryptograficzny), nie czytelną konkatenacją —
inaczej ponownie zdradzałaby strukturę/pochodzenie. Wybór konkretnej funkcji
skrótu to czysty detal implementacyjny, poza zakresem tego dokumentu.

Routing wywołania: Gateway mapuje opaque ID na (Plugin, wewnętrzne odniesienie
tego Pluginu) — nigdy bezpośrednio na integrację. Dalsze rozwiązanie do
konkretnej integracji jest wewnętrzną sprawą Pluginu.

### 4.3 Satelita → pokój: dwuetapowa rejestracja
Rdzeń zna wyłącznie opaque ID satelity (wiedza o pochodzeniu requestu, tego
samego rodzaju co `session_id`) — nigdy nie wie, że odpowiada jakiemukolwiek
pokojowi. Mapowanie ID → pokój jest prywatną wiedzą pluginu Smart Home,
ustawianą w jego własnej konfiguracji.

### 4.4 Grupy jako w pełni wewnętrzna sprawa Pluginu
Grupa ("salon_lampki") z definicji może przecinać granice integracji tej
samej domeny — tylko Plugin, widzący wszystkie swoje integracje naraz, ma
fizyczną możliwość ją zdefiniować i wykonać na niej rozgłoszone wywołanie.
To dlatego Gateway rozmawia wyłącznie z Pluginem, nigdy z integracją wprost —
Plugin oddaje już gotową, spłaszczoną listę encji, w której grupa jest po
prostu kolejną pozycją, nieodróżnialną z zewnątrz od pojedynczego urządzenia.
Definicja grupy (jej skład) mieszka w tej samej, prywatnej, plugin-wide
konfiguracji co mapowanie satelita→pokój (sekcja 4.3) — nie w konfiguracji
pojedynczej integracji, nawet jeśli dziś wszyscy członkowie grupy pochodzą
z jednej.

Konsekwencja: Gateway pozostaje w pełni **jednoprzebiegowy** — nie potrzebuje
żadnej specjalnej kategorii uczestnika do obsługi grup.

---

## 5. Miejsce pojęć domenowych

"Encja" jako generyczny kształt żyje w Kontrakcie. Konkretna jej realizacja
(np. `Device` ze Smart Home) jest pojęciem konkretnego Pluginu, nie rdzenia.
Inny plugin miałby własną nazwę i pola dla swojej wersji tego samego kształtu.

---

## 6. Świadomie zaakceptowane kompromisy

- **Miękkie sprzężenie nazewnicze** między Dostawcą kontekstu (satelita) a
  Pluginem interpretującym jej ID — oparte na konwencji, nie formalnym
  kontrakcie. Jedyne miejsce w systemie, gdzie dwa niezależne moduły muszą
  "domyślić się" tej samej etykiety.
- **Spójność słownika między integracjami wewnątrz jednego Pluginu** nie jest
  wymuszona przez architekturę — to odpowiedzialność autora Pluginu, choć
  tańsza niż w poprzedniej wersji tej wizji, bo dotyczy kodu w całości
  napisanego i utrzymywanego przez jednego autora, nie dwóch niezależnych modułów.
- **Dwuetapowa rejestracja** (sekcja 4.3) — koszt przyjęty w zamian za to, że
  rdzeń nigdy nie musi wiedzieć, że plugin Smart Home istnieje.

---

## 7. Co zostaje bez zmian względem dzisiejszego systemu

Warstwowość i jednokierunkowa zależność, świeże budowanie kontekstu przy
każdej turze, konfiguracja w plikach JSON, filozofia jawnej rejestracji
zamiast dynamicznego ładowania pluginów (YAGNI, `manifest.md` sekcja 5).

## 8. Co znika lub zmienia rolę względem dzisiejszego kodu

- **Addon jako właściciel modelu i logiki** — znika, zastąpiony przez Plugin.
- **Dopasowywanie po nazwie** (`_resolve`) — znika, zastąpione opaque ID.
- **`Device`/`DeviceGroup` jako współdzielony model addonu** — zostają jako
  pojęcia należące do konkretnego Pluginu (sekcja 5), grupa w pełni rozwiązana
  wewnątrz niego, zanim Gateway w ogóle ją zobaczy.
- **`get_extra_tools()`** — rozpuszcza się, integracja po prostu implementuje
  dodatkowy Kontrakt.
- **Kompozytor jako osobna, Gateway-poziomowa kategoria** — usunięty z tej
  wizji względem wcześniejszej wersji dokumentu. Superseded przez: Gateway
  rozmawia wyłącznie z Pluginem (sekcja 4.4), pozostaje w pełni jednoprzebiegowy.

---

## 9. Poza zakresem — świadomie odłożone

- **Grupy międzypluginowe** (np. scena łącząca światło i muzykę z dwóch
  różnych pluginów) — żaden Plugin nie ma wglądu w drugi, więc to wymagałoby
  odtworzenia Gateway-poziomowego mechanizmu kompozycji, którego ta wizja
  świadomie unika. Do rozważenia dopiero, gdy pojawi się realna potrzeba.
- **Automatyzacje/skrypty** (np. "wychodzę" = zgaś światła + zablokuj drzwi +
  ustaw termostat) — sekwencja **różnych** czasowników, nie rozgłoszenie
  jednego na wiele encji. To odrębne pojęcie od grupy, celowo tu nierozwijane.

---

## 10. Status otwartych punktów

Wszystkie punkty otwarte podczas tej sesji projektowej zostały rozstrzygnięte
(sekcje 4.2 i nagłówek dokumentu). Jedyny pozostały detal — konkretna funkcja
skrótu użyta do wyliczania opaque ID — jest świadomie pozostawiony jako
decyzja implementacyjna, nie architektoniczna.
