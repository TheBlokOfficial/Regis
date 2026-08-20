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
python -m uv run --package desktop_satellite python -m desktop_satellite.main --sender-id moj_komputer
```

Opcje: `--server-url` (domyślnie `ws://127.0.0.1:8000/ws/voice`), `--log-level`.

Przed pierwszym uruchomieniem zarejestruj `sender_id` w Web UI (zakładka
**Świat → Nadawcy**), żeby satelita miała przypisany pokój — bez tego agent
nadal odpowie, ale bez kontekstu lokalizacji.
