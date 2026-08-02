# Regis Project Handoff

## Ostatnia Sesja (Zrealizowano)
- **Restrukturyzacja LLM Backends (Faza 2 czyszczenia):** Przeniesiono cały katalog `src/core/llm_backends/` do `src/controller/llm_backends/`. Usunięto z domeny `core/` logikę, która należy wyłącznie do zarządzania dostawcami modeli wewnątrz Kontrolera.
- **Aktualizacja Zależności:** Wszystkie wewnętrzne odwołania w kontrolerze (w tym `providers.py`, `openrouter_backend.py`, `chat_service.py`), jak również referencje ze zgodnością wsteczną w silnikach (`src/node/engines/llm_engine.py` i `src/worker/engines/llm_engine.py`) zaktualizowano tak, by korzystały z `controller.llm_backends`.
- **Weryfikacja (QA):** Uruchomiono `pytest` wektorujący wszystkie powiązane z backendami testy, zachowując 100% pozytywny wynik. Brak jakichkolwiek "sierot" importowych po `core.llm_backends` w projekcie.

## Aktualny stan kodu
Architektura w warstwie abstrakcji modeli LLM została uprzątnięta. Logika specyficzna dla routingu modeli znajduje się teraz całkowicie w podsystemie Kontrolera, zostawiając folder `core/` wyłącznie dla współdzielonych schematów i podstawowych interfejsów (które i tak nie powinny trzymać hardcodowanych logik poszczególnych backendów). System i testy działają stabilnie.

## Kroki Startowe dla Nowego Agenta
1. Zapoznaj się z plikami `docs/MANIFEST.md` i `docs/AGENT_GUIDE.md`, aby uszanować rozstrzygnięte decyzje architektoniczne.
2. Odpal polecenie `pytest` w korzeniu projektu w celu upewnienia się, że nie wystąpiła żadna regresja.
3. Przejdź do `.agents/TASKS.md`, by podjąć kolejne zadanie (np. dociągnięcie abstrakcji w STT/TTS lub kwestie instalatora Windows).
