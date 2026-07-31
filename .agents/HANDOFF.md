# Przekazanie Sesji (Handoff)

## Ostatnia Sesja: Wdrożenie TTS (Text-to-Speech) - Faza 1 (Piper)

### Co zostało zrobione w tej sesji:

- **Architektura Przesyłu Dźwięku (Base64 + SSE):**
  - Stworzono nowy moduł `src/core/tts_engine.py` (początkowo na silniku `piper-tts`), który generuje mowę w locie i koduje ją do formatu Base64 (`.wav`).
  - W `src/node/worker.py` (pętla ReAct) dodano przechwytywanie ostatecznego tekstu odpowiedzi, syntezę audio i wysyłkę zdarzenia `"tts_audio"` przez Server-Sent Events do Kontrolera (tuż przed zdarzeniem `"done"`).
  - W `src/node/satellite.py` zaimplementowano obsługę `"tts_audio"`: dekodowanie Base64 i synchroniczne odtwarzanie przez bibliotekę `sounddevice`. Synchroniczność (`sd.wait()`) zapobiega nagrywaniu własnej mowy przez Satelitę jako nowej komendy.

- **Rozwiązane problemy techniczne:**
  - Zdiagnozowano i naprawiono błąd z `ModuleNotFoundError` (paczki instalowane globalnie zamiast w izolowanym środowisku projektu `.venv`).
  - Zdiagnozowano problem z Zaporą systemu Windows (Firewall), która blokowała "Heartbeat" od Kontrolera na porcie `8001` po zmianie ścieżki pliku `python.exe` na ten z `.venv` (skutkowało to kodem HTTP 503).
  - Naprawiono różnice w API paczki `piper-tts` (użyto poprawnej metody `synthesize_wav`).

- **Decyzje projektowe i pivot technologiczny:**
  - Użytkownik przetestował model Piper (głosy "gosia" oraz "darkman"), jednak całkowicie odrzucił jakość brzmienia jako "zbyt nienaturalną i przypominającą robota po wylewie".
  - Zaplanowano przejście na model **Coqui XTTS v2** działający w 100% offline na procesorze głównym (CPU). Użytkownik dysponuje procesorem Ryzen 5 9600X, co zniweluje narzut czasowy do około 1-1.5s na generację.
  - Opracowano koncepcję **"Incepcji Głosowej"** dla XTTS v2: użytkownik nie chciał klonować prawdziwej osoby, więc próbką referencyjną będzie *syntetyczne, wygenerowane uprzednio przez stary model Piper nagranie*. XTTS v2 użyje go jako ziarna, by stworzyć płynny, głęboki, ale w 100% oryginalny, nienależący do żadnego żywego człowieka głos AI.

### Aktualny stan kodu:
- System działa pomyślnie z modelem `piper-tts`. Zależności, przesył SSE, dekodowanie i odtwarzacz w Satelicie są gotowe. Kod znajduje się na masterze.

### Wskazówki startowe dla następnego agenta:
1. **PIERWSZY KROK:** Następną iterację należy rozpocząć od zastąpienia modułu Piper w `src/core/tts_engine.py` pakietem `TTS` (Coqui) i modelem `xtts_v2` inicjalizowanym z flagą `gpu=False`.
2. Zaktualizuj plik `implementation_plan.md` jeśli uzyskasz zgodę użytkownika na wdrożenie "Incepcji Głosowej" (opisanej w logach z poprzedniej sesji).
3. Do próbki referencyjnej należy najpierw jednorazowo wygenerować starym Piperem plik `.wav` (np. ze zdaniem "Regis gotowy do pracy, proszę pana"), zapisać go w `data/models/voice_sample.wav` i podać jako referencję (parametr `speaker_wav`) do XTTS v2. Następnie usunąć zależność `piper-tts` z projektu.
4. Przed jakimikolwiek modyfikacjami upewnij się, że instalujesz nowe pakiety w lokalnym środowisku wirtualnym: `.\.venv\Scripts\pip install ...`.
