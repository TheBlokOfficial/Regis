# Przekazanie Sesji (Handoff)

## Ostatnia Sesja: Wdrożenie i stabilizacja Fazy 1 (System Providerów LLM)

### Co zostało zrobione w tej sesji:

1. **Wdrożenie Fazy 1 na produkcję:**
   - Zakończono implementację `llm_backends/` (Ollama, OpenRouter).
   - Skonfigurowano `router.py` i `providers.py` do dynamicznego wybierania LLM-ów.
   - Usunięto konflikty promptowe: usunięto przestarzałe instrukcje XML (`<action>`) z `tier_regis.md`, wymuszając na OpenRouterze czyste, natywne Function Calling (OpenAI format).
   
2. **Naprawa błędów integracyjnych:**
   - Poprawiono logikę fetchowania narzędzi w `openrouter.py` (użycie `get_tools_for_tier` zamiast błędnej właściwości).
   - Załatano bug w interfejsie graficznym / CLI (Dashboard / Satelita). Klient `remote_client.py` nasłuchiwał na event typu `"tool"`, podczas gdy backend wysyłał poprawny event `"tool_call_raw"`. Powodowało to niewidzialność logów narzędzi przy włączonym `/verbose`.
   
3. **Logika Priorytetyzacji (Fallback):**
   - Skonfigurowano inteligentny system priorytetów backendów w `providers.py` i `router.py`:
     1. **Lokalny Worker (tier = 'regis')** — najpotężniejszy lokalny komputer (np. stacjonarka RTX-5070), priorytet darmowego działania.
     2. **Chmura (OpenRouter)** — główny awaryjny fallback, na wypadek gdyby główny komputer był wyłączony.
     3. **Lokalny Worker (tier = 'butler')** — ostateczny fallback (np. Raspberry Pi), działający w przypadku braku Internetu i braku głównego komputera.

### Kluczowe decyzje architektoniczne podjęte w tej sesji:

- **Natywne Function Calling w chmurze działa:** Potwierdzono, że nowsze modele (np. Qwen 3.7 Flash) poprawnie interpretują przekazane narzędzia bez potrzeby tworzenia formatu XML. Narzędzia są przesyłane w ustandaryzowanym formacie i odbierane z powrotem.
- **Odpowiedzialność narzędzi:** Model ma dostęp do inteligentnego `get_device_state`. W przypadku awarii fizycznego urządzenia (np. Yeelight odcięty od prądu), model najpierw to weryfikuje, unikając bezsensownego wysyłania komendy `turn_on`.

### Wskazówki startowe dla następnego agenta:

1. **ZADANIE DO ROZPOCZĘCIA:** System jest w pełni gotowy do rozpoczęcia **Fazy 2: Abstrakcja STT/TTS backends**. 
2. Należy przenieść logikę STT i TTS na system "provider-agnostic" na wzór modułu `llm_backends/`. W Kontrolerze docelowo powinno być możliwe korzystanie z TTS w chmurze bez polegania wyłącznie na lokalnym węźle Windows.
3. Przed zmianą czegokolwiek, skonsultuj plik `docs/llm_providers_rfc.md` (jeśli ma informacje o TTS/STT) lub stwórz nowy dokument RFC dla Fazy 2.
