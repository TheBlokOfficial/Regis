# RFC: Nowy System Dystrybucji `node` (Windows)

> **Ten dokument jest decyzją architektoniczną podjętą w sesji użytkownika.**
> Opisuje uzgodniony kierunek zmiany systemu budowania i dystrybucji dla Windows.
> Nie zawiera kodu — zawiera precyzyjną wizję tego co ma powstać i dlaczego.
> Implementacja zaplanowana jako **Sesja E**.

---

## 1. Problem — Dlaczego Rezygnujemy z PyInstallera

Obecna dystrybucja `node` opiera się na PyInstallerze (`--onedir`).
Zidentyfikowano następujące wady, które sklasyfikowano jako nie do zaakceptowania:

1. **Efekt czarnej skrzynki.** Skompilowana binarka jest nieprzeźroczysta. Nie wiadomo co
   się w środku dzieje, co utrudnia diagnozowanie problemów i narusza filozofię projektu
   (kontrola i przejrzystość).

2. **Podejrzany wygląd dystrybucji.** Jeden plik `.exe` + dwa foldery (`_internal/`, `data/`)
   wygląda nieprofesjonalnie i często jest flagowany przez programy antywirusowe, ponieważ
   mechanizm rozpakowywania PyInstallera jest charakterystycznym wzorcem malware.

3. **Opóźnienie startu (Bootloader).** Mimo trybu `--onedir` (który nie rozpakowuje przy
   każdym starcie), sam bootloader PyInstallera dodaje odczuwalną latencję przy uruchamianiu
   aplikacji — sprzeczne z wymaganiem natychmiastowego startu.

4. **Opóźnienie separacji warstw UX.** Podział na "Pilot" (konsola CLI) i "Usługę" (tray)
   był trudny do czytelnego rozróżnienia w modelu PyInstaller — zlewa się w jedną, niejasną
   całość dla użytkownika.

5. **Drogi workflow deweloperski.** Każda zmiana jednej linijki kodu wymagała pełnej
   rekompilacji projektu (kilka minut). Niedopuszczalne przy aktywnym rozwoju.

---

## 2. Decyzja — Nowy System Dystrybucji

### Wybrane podejście: Windows Installer (.exe) + Python jako prerequisite systemowy

Odrzucono dwie alternatywy:

| Podejście | Odrzucone, bo |
|---|---|
| PyInstaller (obecny) | Wszystkie wady opisane w §1 |
| Portable Embedded Python | Nadal "folder ze skryptami", brak natywnej integracji z Windowsem, wymaga budowania artefaktu |

Wybrane podejście polega na rozdzieleniu dwóch niezależnych warstw:

- **Warstwa instalacji** — jednorazowy, profesjonalny installer `.exe` (Inno Setup)
- **Warstwa runtime** — Python systemowy + pakiet `regis[node]` zainstalowany przez pip

### Narzędzie buildowe: Inno Setup

Inno Setup to darmowy, open-source kreator instalatorów Windows.
Stosują go projekty tej klasy co Python.org (oficjalny installer Pythona).
Produkuje pojedynczy plik `RegisNodeSetup.exe`.

---

## 3. Co Robi Installer (RegisNodeSetup.exe)

Sekwencja działań instalatora przy pierwszym uruchomieniu na czystej maszynie:

```
RegisNodeSetup.exe
  → Sprawdza: czy Python 3.11+ jest zainstalowany w systemie?
      Nie → Pobiera i instaluje Python 3.12 cicho (tryb /quiet z python.org)
      Tak → Kontynuuje
  → Tworzy katalog instalacji: C:\Program Files\Regis-Node\
  → Kopiuje pliki aplikacji (kod źródłowy .py) do katalogu instalacji
  → Uruchamia: pip install regis[node]
  → Tworzy skrót w Menu Start: "Regis Node"
  → Rejestruje wpis w "Dodaj/Usuń programy" (Uninstaller)
  → (Opcjonalnie) Pyta czy dodać do autostartu
```

### Struktura po instalacji

```
C:\Program Files\Regis-Node\
├── app\                    ← kod źródłowy .py (widoczny, edytowalny)
│   ├── node\
│   ├── core\
│   └── integrations\
├── data\                   ← konfiguracja użytkownika (settings.json)
└── Uruchom.bat             ← cienki wrapper wywołujący `regis-node` (entry point)
```

Plik `Uruchom.bat` to po prostu:
```bat
@echo off
regis-node
```

Żadnych binarek. Żadnych skompilowanych plików. Czysty Python.

---

## 4. Dwa Tryby Pracy (Developer vs. User)

### Tryb Deweloperski (aktywny rozwój)

Installer w ogóle nie jest używany.
Developer pracuje bezpośrednio na repozytorium:

```bat
pip install -e .[node]   ← jednorazowo ("editable install" — linkuje do src/)
regis-node               ← uruchamia się prosto z kodu źródłowego
```

Zmiana jednej linijki w kodzie jest aktywna natychmiast przy następnym uruchomieniu.
Zero rekompilacji. Zero czekania. Pełne stacktrace z numerami linii.

### Tryb Produkcyjny (release)

Używany tylko gdy chcemy przekazać paczkę innemu urządzeniu lub użytkownikowi.

```bat
regis build-installer   ← nowa komenda w regis_cli (patrz §5)
```

Produkuje `dist\RegisNodeSetup.exe`.

---

## 5. Zmiany w `regis_cli`

`regis_cli/builders.py` wymaga aktualizacji:

### Do usunięcia
- Funkcja `build_portable_windows()` — logika PyInstaller. Nieaktualna.
- Wszelkie referencje do `PyInstaller`, `--onedir`, `--hidden-import pystray._win32`.

### Do dodania
- Funkcja `build_installer_windows()` — generuje skrypt `.iss` (Inno Setup Script)
  i wywołuje kompilator Inno Setup (`ISCC.exe`) jeśli jest dostępny w PATH.
- Skrypt `.iss` może być generowany dynamicznie (z wersją z `pyproject.toml`) lub
  przechowywany jako statyczny szablon `regis-node.iss` w katalogu głównym projektu.

### Nowa komenda w menu `regis_cli`
Dodać opcję "Zbuduj Installer Windows (.exe)" w głównym menu `regis_cli/main.py`.

---

## 6. Zmiany w `pyproject.toml`

Stare extras `[worker]` i `[satellite]` mogą zostać usunięte — ich zawartość jest już
skonsumowana przez `[node]`. Przed usunięciem agent powinien sprawdzić czy cokolwiek
jeszcze je referuje (w szczególności skrypt deploymentu na RPi).

Wpis `regis-worker` w `[project.scripts]` do usunięcia (pakiet `controller.worker` przestał istnieć).

---

## 7. Zmiany w `regis_cli/deployers.py`

Skrypt deploymentu na Raspberry Pi (SSH) zawiera komendę:
```
rm -rf controller/ controller/worker/ regis_satellite/ regis_terminal/ ...
```

Po usunięciu starych pakietów ta komenda powinna zostać uproszczona do:
```
rm -rf controller/ core/ integrations/
```

Referencja do `regis-worker.service` w komendzie restart (`systemctl`) wymaga
wyjaśnienia z użytkownikiem — po usunięciu `controller.worker` nie jest jasne jaką
usługę uruchamia RPi jako fallback worker. **Agent realizujący Sesję D/E powinien
zapytać użytkownika o tę kwestię zanim dotknie deployers.py.**

---

## 8. Prerequisity dla Implementacji (Sesja E)

Aby zrealizować ten RFC, agent potrzebuje:

1. **Inno Setup zainstalowany na maszynie deweloperskiej** (Windows).
   Dostępny za darmo: https://jrsoftware.org/isinfo.php
   Agent powinien sprawdzić czy `ISCC.exe` jest w PATH przed próbą budowania.

2. **Sesja D zakończona** — stare pakiety (`regis_satellite`, `regis_terminal`) muszą być
   usunięte zanim budujemy nowy installer.

   > **Uwaga krytyczna:** `controller.worker` **NIE jest usuwany** w Sesji D.
   > Zostaje jako oddzielny, headless worker dla Linux/RPi5 (usługa systemd bez UI i audio).
   > Jest to świadoma decyzja architektoniczna — RPi5 to serwer bez peryferiów audio,
   > a `node` jest pakietem wyłącznie Windows. To dwa różne deployment targety.
   > Szczegóły uzasadnienia: sesja architektoniczna 2026-07-26.

---

## 9. Decyzje Podjęte (Nie Otwieraj Ponownie)

| Decyzja | Szczegół |
|---|---|
| Porzucamy PyInstaller | Wady §1. Ostateczna, bez wyjątków. |
| Python jako prerequisite systemowy | Akceptowalny — installer instaluje go automatycznie |
| Narzędzie: Inno Setup | Darmowe, profesjonalne, używane przez Python.org |
| Brak Embedded Python | Odrzucony — "folder ze skryptami" bez integracji z Windows |
| Developer workflow: `pip install -e .` | Standard Python, bez żadnych zmian względem obecnych praktyk |
| Installer jest krokiem release, nie dev | Nie blokuje codziennego developmentu |

---

## 10. Co Absolutnie Nie Ulega Zmianie

- Architektura runtime `node` (System Tray, wizard, procesy w tle) — bez zmian
- Wizard konfiguracyjny (questionary → `settings.json`) — bez zmian
- Protokół Controller ↔ Node (HTTP + SSE) — bez zmian
- Deployment Kontrolera na RPi (`.whl` + SSH) — bez zmian
- Wszystkie decyzje z `MANIFEST.md` i `AGENT_GUIDE.md` — bez zmian
