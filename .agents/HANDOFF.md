# Przekazanie Sesji (Handoff)

## Ostatnia Sesja: Pivot Architektoniczny — System Providerów LLM

### Co zostało zrobione w tej sesji:

**Zmiany koncepcyjne i dokumentacyjne (kod NIE był modyfikowany):**

1. **Rewizja filozofii projektu** — z "local only" na "provider-agnostic".
   System nie jest już lokalny z założenia. Chmura (OpenRouter) i lokalne modele
   (Ollama) są równorzędnymi providerami. Wybór zależy od dostępności, nie ideologii.

2. **Aktualizacja `docs/MANIFEST.md`:**
   - §3.2 — RPi5 Worker: nowa rola (Parser offline + awaryjny STT), nie "komponent przejściowy"
   - §3.3 — Windows Node: opcjonalny lokalny provider, nie wymagany produkcyjnie
   - §3.6 — Wizja Docelowa: mini PC zastąpiony przez RPi5 + chmura; nowy diagram z warstwą PROVIDERÓW
   - §5 — "Dwa Tryby Pracy" zastąpione przez "System Providerów i Degradacja":
     dwustanowa degradacja (pełny / fallback), tabela providerów z priorytetami
   - §7 — dodano nowy dług techniczny: warstwa abstrakcji `llm_backends/` niezaimplementowana

3. **Aktualizacja `docs/AGENT_GUIDE.md`:**
   - Tabela "Decyzje Już Podjęte": usunięto "Brak chmurowych API", zaktualizowano
     opis Parsera i `controller.worker`, dodano 4 nowe decyzje
   - Błąd #5: zmieniono z "nie proponuj chmury" na "nie tight-couplinguj do providera"
   - Sekcja LLM: tier = pojęcie promptu, nie routingu; aktualizacja opisu trybu `regis`

4. **Stworzono `docs/llm_providers_rfc.md`** — kompletny plan restrukturyzacji kodu
   pod nową architekturę. To jest dokument startowy dla następnej sesji implementacyjnej.

### Kluczowe decyzje architektoniczne podjęte w tej sesji:

- **Provider agnosticism:** STT, LLM i TTS mają niezależne rejestry providerów
- **Priorytet LLM:** Cloud > Lokalny (jakość); STT/TTS: Lokalny > Cloud (koszt)
- **Dwustanowa degradacja:** pełny tryb gdy komplet providerów, fallback gdy brakuje ≥1
- **Parser = offline fallback:** nie filtruje w ścieżce krytycznej gdy internet działa
- **OpenRouter:** domyślny provider LLM (modele OSS przez API)
- **Klucz OpenRouter:** konfigurowany tylko na RPi5 (`.env` Kontrolera)

### Aktualny stan kodu:

- Kod NIE BYŁ modyfikowany w tej sesji — to była sesja architektoniczna
- `src/core/llm_engine.py` — nadal Ollama-only (wymaga refaktoryzacji wg RFC)
- `src/core/gemini_engine.py` — nadal istnieje jako eksperyment (do usunięcia po migracji)
- `src/controller/router.py` — nadal tier-based routing (wymaga refaktoryzacji wg RFC)
- `src/controller/registry.py` — nadal ma `_TIER_PRIORITY` (do usunięcia)

### Wskazówki startowe dla następnego agenta:

1. **PIERWSZY KROK:** Przeczytaj `docs/llm_providers_rfc.md` — to jest kompletny
   plan implementacyjny gotowy do realizacji. Zawiera kolejność kroków, mapę zależności
   i plan testów.

2. **Sekwencja implementacji:**
   ```
   1. src/core/llm_backends/base.py
   2. src/core/llm_backends/ollama.py
   3. src/core/llm_backends/openrouter.py  (wzoruj się na gemini_engine.py)
   4. src/core/llm_engine.py (refactor na fabrykę)
   5. src/core/config.py (dodaj OPENROUTER_API_KEY, usuń frozen dead code)
   6. src/controller/providers.py (nowy moduł)
   7. src/controller/registry.py (usuń _TIER_PRIORITY)
   8. src/controller/router.py (provider-based routing)
   9. .env.example (nowe klucze)
   10. DELETE src/core/gemini_engine.py
   ```

3. **Kluczowa uwaga:** Phase 1 RFC dotyczy TYLKO LLM. STT i TTS pozostają bez zmian.
   Audio pipeline nadal idzie przez workerów. Phase 2 (osobna sesja) doda cloud STT/TTS.

4. **Test weryfikacyjny po wdrożeniu:** Uruchom Kontroler z `OPENROUTER_API_KEY`,
   bez żadnego workera, wyślij zapytanie tekstowe — powinno odpowiedzieć z chmury.
