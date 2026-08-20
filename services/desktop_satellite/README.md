# desktop_satellite

Satelita głosowa działająca jako długo działający proces na Windows/Linux
Desktop. Łączy się z serwerem Regis przez `WS /ws/voice/{sender_id}`,
przechwytuje mikrofon, odtwarza audio TTS i przechodzi pełny cykl protokołu
opisany w `shared.voice_protocol`.

Wake-word jest dziś wykrywany po stronie serwera (placeholder
`ThresholdEnergyWakeWordDetector`) — satelita ciągle strumieniuje mikrofon w
stanie nasłuchu. Koniec wypowiedzi (`utterance_end`) wykrywa lokalnie, przez
prosty detektor ciszy (`desktop_satellite.vad.SilenceVadDetector`).

## Uruchomienie

Wymaga uruchomionego serwera (`python -m uv run --package server python -m server.main`).

```bash
python -m uv run --package desktop_satellite python -m desktop_satellite.main
```

Bez żadnych flag: przy pierwszym uruchomieniu satelita generuje trwały
`sender_id` (UUID4) i zapisuje go w `config/settings.json` — kolejne starty
używają tego samego ID. Adres serwera znajduje automatycznie przez UDP
broadcast (`desktop_satellite.discovery`, patrz `docs/manifest.md` sekcja
3.7) — nie trzeba ręcznie wpisywać IP.

Opcje:
- `--server-url` — pomija auto-discovery, np. gdy satelita jest w innej
  podsieci niż serwer (`ws://192.168.1.10:8000/ws/voice`).
- `--sender-id` — pomija trwały UUID z pliku, przydatne np. do testów.
- `--log-level` — domyślnie `INFO`.

Po pierwszym uruchomieniu zarejestruj wygenerowany `sender_id` (widoczny w
logu startowym, albo w `config/settings.json`) w Web UI (zakładka **Świat →
Nadawcy**), żeby satelita miała przypisany pokój — bez tego agent nadal
odpowie, ale bez kontekstu lokalizacji.
