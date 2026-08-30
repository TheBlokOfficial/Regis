# desktop_satellite

Satelita głosowa działająca jako długo działający proces na Windows/Linux Desktop.
Łączy się z serwerem Regis przez `WS /ws/voice/{sender_id}`, przechwytuje mikrofon,
odtwarza audio TTS i przechodzi pełny cykl protokołu opisany w `shared.voice_frames`.

Wake-word wykrywa **serwer** — satelita ciągle strumieniuje mikrofon w stanie nasłuchu.
Koniec wypowiedzi (`utterance_end`) wykrywa lokalnie, przez prosty detektor ciszy
(`desktop_satellite.vad.SilenceVadDetector`) o progach skonfigurowanych centralnie
i przysłanych przy handshake.

---

## Postać produkcyjna (zalecana)

Aplikacja bez okna, z ikoną w zasobniku systemowym.

```bash
# Windows
.\build.ps1
.\install.ps1

# Linux
./build.sh
./install.sh
```

`build` przygotowuje `dist/regis-satellite/` (PyInstaller, `--onedir --noconsole`),
`install` kopiuje to do katalogu programu użytkownika, tworzy skrót i przenosi
dotychczasowy `sender_id`, jeśli satelita była wcześniej uruchamiana ze źródeł.

### Pierwsze uruchomienie

1. Uruchom aplikację — w zasobniku pojawi się ikona (szara: szuka serwera, zielona: połączona).
2. Z menu ikony skopiuj `sender_id`.
3. W Web UI serwera: **Ustawienia → Klienci** zatwierdź nadawcę, **Świat → Nadawcy**
   przypisz mu pokój. Bez tego agent nadal odpowie, ale bez kontekstu lokalizacji.
4. Jeśli chcesz, włącz w menu **Uruchamiaj przy starcie systemu**.

Menu zasobnika nie jest ozdobą: w trybie bezokienkowym to jedyny sposób odczytania
`sender_id`, sprawdzenia stanu połączenia i dotarcia do logów.

### Gdzie co leży

| Co | Windows | Linux |
| :--- | :--- | :--- |
| Program | `%LOCALAPPDATA%\Programs\Regis` | `~/.local/share/regis` |
| Konfiguracja (`sender_id`) | `%APPDATA%\Regis\settings.json` | `~/.config/regis/settings.json` |
| Logi | `%APPDATA%\Regis\logs\satellite.log` | `~/.config/regis/logs/satellite.log` |
| Autostart | `HKCU\...\CurrentVersion\Run` | `~/.config/autostart/regis-satellite.desktop` |

Adres serwera znajduje automatycznie przez UDP broadcast (`desktop_satellite.discovery`)
— nie trzeba niczego wpisywać. Po stronie satelity nie ma żadnej konfiguracji poza
włącz/wyłącz i autostartem; wszystkim steruje serwer.

---

## Uruchomienie ze źródeł (praca nad kodem)

```bash
python -m uv run --package desktop_satellite python -m desktop_satellite.main --console
```

`--console` to dawne zachowanie: bez zasobnika, logi na wyjście, zatrzymanie Ctrl+C.
Tryb ten włącza się też sam, gdy `pystray`/`Pillow` nie są zainstalowane (są w grupie
zależności `build`, nie w podstawowych) — uruchomienie ze źródeł nie wymaga więc
niczego ponad zwykłe `uv sync`.

W tym trybie konfiguracja żyje w `services/desktop_satellite/config/settings.json`,
a nie w katalogu użytkownika. To dwie różne lokalizacje, więc przejście na wersję
zainstalowaną bez przeniesienia pliku dałoby **nowy `sender_id`** — robią to za Ciebie
skrypty `install.*`.

Opcje: `--server-url` (pomija auto-discovery), `--sender-id` (pomija plik konfiguracji),
`--log-level`, `--console`.

---

## Pułapki buildu (rozbrojone, warto wiedzieć)

* **PortAudio** nie jest widoczne dla statycznej analizy PyInstallera — dołącza je hook
  `hook-sounddevice.py`, a `build.*` **sprawdza jego obecność w gotowym bundlu**. Brak
  tej biblioteki nie wywala builda, tylko aplikację, i to dopiero przy pierwszym
  wake-wordzie.
* **Interpreter**: budujemy samodzielnym Pythonem zarządzanym przez `uv`, nie systemowym.
  Build zrobiony na współdzielonym `.venv` monorepo dawał aplikację padającą przy starcie
  na `DLL load failed while importing _ssl`.
* **Brak konsoli** oznacza brak `sys.stdout` — `shared.setup_logging()` pomija wtedy
  handler konsoli, inaczej pierwszy log zabijałby aplikację bez śladu.
* Środowisko graficzne musi obsługiwać ikony zasobnika (GNOME wymaga rozszerzenia
  AppIndicator).
