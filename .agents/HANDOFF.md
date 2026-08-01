# Przekazanie Sesji (Handoff)

## Ostatnia Sesja: Wdrożenie Architektury Zjednoczonego Węzła (Node-Centric) oraz Poprawki VAD & Web UI

### Co zostało zrobione w tej sesji:

1. **Wdrożenie Architektury Zjednoczonego Węzła (Node-Centric Model)**:
   - Przeprojektowano model rejestracji: fizyczna maszyna (PC) rejestruje się pojedynczym wnioskiem `POST /v1/nodes/register` jako **Zjednoczony Węzeł** (`services: ["worker", "satellite"]`) z głównym portem zarządzania `8099`.
   - Zaktualizowano schematy w `src/core/schemas.py`, rejestr w `src/controller/registry.py`, dodano router `src/controller/routers/nodes.py` oraz testy w `tests/test_nodes.py`.
   - Zaktualizowano `src/node/service.py` do zbiorczej rejestracji i wyrejestrowywania całej maszyny.
   - Zaktualizowano routing w `src/controller/services/chat_service.py` oraz `src/controller/routers/ui.py`.
   - Dostosowano panel Web UI w `src/controller/web/events.js` do reaktywnej obsługi zdarzeń Zjednoczonego Węzła.

2. **Naprawa Błędów i Optymalizacja VAD**:
   - **Brak duplikacji rejestracji**: Wstrzymano emitowanie zbędnych zdarzeń `worker_registered` / `node_registered` przy odnawianiu sesji co 15s w routerach Kontrolera.
   - **Trwałe timestampy w Web UI**: W `src/controller/event_bus.py` oraz `src/node/service.py` dodano automatyczne stemplowanie czasu utworzenia zdarzenia (`timestamp`), co zapobiega nadpisywaniu historycznych godzin czasem odświeżenia strony.
   - **Karta Węzła w UI**: Zastąpiono usunięte pole `Tier` wartością `Priorytet` (`priority`) w `src/controller/web/renderer.js`.
   - **Ciągłe śledzenie i Histereza VAD**: W `src/node/satellite.py` dodano wygładzanie (hangover 400ms) w `EnergyVAD`, eliminując szatkowanie mowy.
   - **Bramkowanie i Pre-buffer Feed w WakeWord**: Zoptymalizowano `_handle_wakeword()` – dopóki panuje cisza, VAD ignoruje inferencję ONNX (oszczędność procesora). Przy wystąpieniu mowy VAD nakarmia sieć neuronową zaległym buforem `ring_buffer` (pre-buffer context) oraz używa czułego progu `SILENCE_THRESHOLD = 150`, zapewniając błyskawiczne i nieprzerwane wybudzanie na słowo *"Regis"*.

3. **Weryfikacja i Deployment**:
   - Przetestowano cały pakiet testów `pytest` (33/33 passed).
   - Odbudowano i wysłano zaktualizowaną paczkę Kontrolera na Raspberry Pi (`tools/build_controller.py`).

---

### Aktualny stan kodu:
Architektura Zjednoczonego Węzła oraz mechanizm detekcji VAD/WakeWord są w pełni wdrożone, przetestowane, zdeployowane na Raspberry Pi i zapisane w repozytorium Git.

---

### Wskazówki startowe dla następnego agenta:

1. **Kolejne zadania z `TASKS.md`**:
   - **[ARCH — Phase 2]**: Abstrakcja STT/TTS backends + split audio pipeline w Kontrolerze (cloud STT/TTS bez Windows Node).
   - **[WORKER PROFILE SWAP]**: Mechanizm ręcznego przełączania modelu workera na desktopie Windows między trybem Butler (mały model) a trybem Regis (model 9B).
   - **Migracja TTS na model Coqui XTTS v2** / **Pamięć Długoterminowa**.
