# Przekazanie Sesji (Handoff)

## Ostatnia Sesja: Weryfikacja Fallbacku i Debugowanie Qwen 3 (Reasoning)

### Co zostało zrobione w tej sesji:

1. **Weryfikacja priorytetyzacji (Fallback):**
   - Zweryfikowano działanie mechanizmu fallback (skok z zepsutej chmury OpenRouter na lokalnego RPi5).
   - Odkryto i załatano błąd "głuchego telefonu" – worker wysyłał logi jako `tool`, a UI nasłuchiwało na `tool_call_raw`. Zaktualizowano `worker.py` (i `server.py`), aby nazewnictwo eventów się zgadzało.

2. **Debugowanie modeli Reasoning (Qwen 3) + Structured Outputs:**
   - Zweryfikowano problem z `qwen3` połączonym ze Structured Outputs (`format: json`) oraz flagą `"think": False`.
   - Zdiagnozowano, że pomimo wyłączenia tagów myślenia, model nadal przeprowadza wewnętrzne, powolne rozumowanie na RPi (zajmujące ok. 50-60 sekund).
   - Odkryto błąd ucinań LLMa – sztywny limit `"num_predict": 80` ucinał generację wewnętrznych przemyśleń, powodując zwrot pustego `content` i rzucając wyjątek `JSONDecodeError`. Zwiększono limit w `nlu_agent.py` do 512.
   - Wdrożono przechwytywanie ukrytego pola `thinking` ze strumienia Ollamy w kodzie `nlu_agent.py` oraz `react_agent.py`. Dzięki temu monolog wewnętrzny Qwen 3 jest teraz poprawnie strumieniowany na ekran terminala ("Regis myśli: ..."), aby użytkownik wiedział, co zajmuje czas.

### Kluczowe decyzje architektoniczne podjęte w tej sesji:

- **Brak przymusowego odcinania "myślenia" przy JSON:** Modele takie jak Qwen 3, gdy poprosi się je o sztywny JSON, często muszą wewnętrznie pomyśleć. Opcja `"think": False` w Ollamie przesuwa jedynie myśli do pola `thinking`, ale nie skraca radykalnie czasu wywołania na słabym sprzęcie. Decyzją Użytkownika, aktualny stan zostaje zachowany – wolniejszy fallback jest tolerowany w zamian za wgląd w jego myśli na ekranie. Złota reguła: nie modyfikujemy domyślnego zachowania Workera (RPi) chyba że Użytkownik wyraźnie nakazuje powrót do non-reasoning modelu np. `qwen2.5:1.5b`.

### Wskazówki startowe dla następnego agenta:

1. **ZADANIE DO ROZPOCZĘCIA:** System jest teraz w pełni ustabilizowany na froncie LLM-ów. Rozpocznij **Fazę 2: Abstrakcja STT/TTS backends**. 
2. Należy przenieść logikę STT i TTS na system "provider-agnostic" na wzór modułu `llm_backends/`. W Kontrolerze docelowo powinno być możliwe korzystanie z TTS w chmurze bez polegania wyłącznie na lokalnym węźle Windows.
3. Przed zmianą czegokolwiek, skonsultuj plik `docs/llm_providers_rfc.md` (jeśli ma informacje o TTS/STT) lub stwórz nowy dokument RFC dla Fazy 2.
