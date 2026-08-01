# Przekazanie Sesji (Handoff)

## Ostatnia Sesja: Stabilizacja RPi5, Poprawka NLU JSON Schema, Diagnostyka Profilera i Plan Upgrade'u na Minisforum

### Co zostało zrobione w tej sesji:

1. **Stabilizacja Usług i Naprawa Pętli Awarii na RPi5:**
   - Wykryto i naprawiono przyczynek "wariowania" usług `systemd` (`regis-worker.service`) – brakującą inicjalizację `llm_engine` w `WorkerNode`.
   - Ubito ręczne procesy tle (`nohup`) oraz całkowicie wyłączono przestarzałą usługę `regis-stt.service` (`node/stt_worker.py`), która zbędnie pożerała RAM.
   - Poprawiono skrypt wdrażający [tools/build_controller.py](file:///d:/Projekty/Regis/tools/build_controller.py#L58-L64), usuwając kod, który przy każdym deploymencie wskrzeszał zdeprecjonowaną usługę `regis-stt.service`.

2. **Refaktoryzacja NLU Agent (Oficjalny JSON Schema zamiast Prefix Injection):**
   - Zdiagnozowano błąd `JSONDecodeError` przy modelach z funkcją myślenia (`qwen3:1.7b`), gdzie sztuczka z doklejaniem klamry `{"role": "assistant", "content": "{"}` generowała podwójny wydatek i tagi `</think>`, blokując wykonywanie akcji w Home Assistant.
   - Wycięto hack z prefix injection w [src/core/agents/nlu_agent.py](file:///d:/Projekty/Regis/src/core/agents/nlu_agent.py#L22-L30) i wdrożono oficjalny natywny parametr `"format": "json"` z Ollama API.
   - Zaktualizowano model Butlera na lekki i bardzo szybki **`qwen2.5:0.5b`**, osiągając błyskawiczny czas reakcji komend (~1.0s).

3. **Rozbudowa Diagnostyki i Stopki Profilera w CLI:**
   - Dodano obsługę zdarzeń `on_profiler` w `nlu_agent.py` oraz `ollama.py`.
   - Przywrócono w konsoli CLI pełną stopkę diagnostyczną przy zleceniach NLU (`[TTFT: ... | Gen: ... | Narzędzia: ...]`).

4. **Decyzja Architektoniczno-Sprzętowa (Upgrade do Minisforum UM760 Slim):**
   - Przeanalizowano ograniczenia procesora ARM w RPi5 (TTFT ~550ms przy promptach ~500 tokenów).
   - Użytkownik podjął decyzję o wyprzedaży stacji Raspberry Pi 4 i 5 oraz przesiadce na **Minisforum UM760 Slim (Ryzen 5 7640HS, 16GB DDR5 SO-DIMM, iGPU Radeon 760M)**.
   - Zapewni to skok wydajnościowy (TTFT < 40ms, generowanie 35-50 t/s) i umożliwi uruchamianie pełnych modeli 7B/9B/14B na wymiennych kościach RAM (upgradable do 32GB/64GB).

---

### Kluczowe decyzje architektoniczne podjęte w tej sesji:
- **Natywny JSON zamiast Prefix Injection:** Wszystkie zapytania NLU korzystają wyłącznie z parametru `"format": "json"` lub dedykowanych gramatyk Ollama API.
- **Model Butlera na RPi5:** Ustawiono `qwen2.5:0.5b` jako domyślny lekki model Butlera w [src/node/worker.py](file:///d:/Projekty/Regis/src/node/worker.py#L36-L40) do czasu przesiadki na nową maszynę.

---

### Wskazówki startowe dla następnego agenta:
1. **ZADANIE DO ROZPOCZĘCIA:** Po dostarczeniu nowego komputera Minisforum, przygotować proces migracji Kontrolera i Workera z ARM na architekturę x86_64 Linux.
2. Kontynuować realizację **Fazy 2: Abstrakcja STT/TTS backends** (dostosowanie audio pipeline do wyższych mocy obliczeniowych lub chmury).
