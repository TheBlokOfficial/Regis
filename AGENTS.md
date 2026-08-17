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
Serwer ma dwie warstwy i **żadna nie zna z góry implementacji warstwy poniżej**
— rozszerzenia rejestrują się same, jawnie, w kompozycji aplikacji (`main.py`):

| Warstwa | Katalog | Wie o warstwie niżej tylko tyle |
| :--- | :--- | :--- |
| 0 — Kernel | `server/agent/` | protokół `PluginProvider` (`agent/plugin_contract.py`) |
| 1 — Rozszerzenia | `server/extensions/` | nic — rozszerzenie samo orkiestruje swój backend wewnętrznie (dziś: `HomeAssistantClient`) |

Analogiczna zasada obowiązuje na granicy sieci: `network/gateway.py` zna
wyłącznie protokół `NetworkExtension` (`network/extension_contract.py`) —
`extension_id`/`label`/`is_enabled()`/`set_enabled()`/`build_router()` —
nigdy konkretnego rozszerzenia po nazwie.

Konkretnie: `server/agent/` i `server/network/` nie importują żadnego
rozszerzenia po nazwie (`home_assistant`, `basic_tools`) — jedyne miejsce,
które je zna z imienia, to kompozycja aplikacji w `main.py`. Nowe
rozszerzenie **nigdy** nie wymaga zmiany kernela ani sieci. Weryfikacja
(poprawny wynik: brak trafień w obu):

```bash
grep -rn "from server.extensions" services/server/src/server/agent/
grep -rn "from server.extensions" services/server/src/server/network/
```

Dawny podział na trzy warstwy (Kernel/Pluginy/Integracje z osobnym
kontraktem `DeviceIntegration` i protokołem `ContextProvider`) został
scalony — Integracja to dziś prywatny szczegół wewnętrzny Rozszerzenia,
nigdy widoczny dla Gateway ani sieci. Nie odtwarzaj tego podziału bez
konkretnego przypadku użycia w ręku (patrz `docs/manifest.md`, sekcja
"Świadome decyzje projektowe").

Uzasadnienie i konsekwencje: `docs/manifest.md`, sekcje 3 i 5.

## Jakość kodu
- SOLID, DRY, KISS, YAGNI, Boy Scout Rule.
- Ścisłe typowanie: pełne adnotacje typów w sygnaturach funkcji i metod.
- Logowanie przez wspólny helper: `logger = get_logger("regis.nazwa_modułu")`.
- Testy: `python -m uv run python -m pytest -q`.

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