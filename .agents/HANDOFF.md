# HANDOFF: Stan Projektu Regis

## 1. Wykonane Prace w Ostatniej Sesji

- **Architektura Kanonicznych Mikrousług (`satellite`, `audio`, `llm`)**:
  - Przeprowadzono kompletną dekompozycję monolitycznego Workera (`src/client/services/worker.py` - usunięty).
  - Utworzono 3 czyste, wyspecjalizowane mikrousługi pod `src/client/services/`:
    - [`src/client/services/satellite/`](file:///d:/Projekty/Regis/src/client/services/satellite/): Obsługa mikrofonu, VAD, Wake Word.
    - [`src/client/services/audio/`](file:///d:/Projekty/Regis/src/client/services/audio/): Silnik konwersji głosowej (**STT** Whisper + **TTS** Piper).
    - [`src/client/services/llm/`](file:///d:/Projekty/Regis/src/client/services/llm/): Silnik wnioskowania tekstowego (**LLM** Qwen ReAct + narzędzia HA).

- **Czysty Podział Modułowy (Single Responsibility Principle - SRP)**:
  - Rozbito ciężkie pliki w usługach na wyspecjalizowane moduły:
    - `service.py`: Zarządzanie silnikami w VRAM.
    - `registration.py`: Komunikacja i heartbeat z Kontrolerem.
    - `streaming.py`: Asynchroniczne generowanie ramek SSE.
    - `routes.py`: Deklaratywny router HTTP (FastAPI).
    - `app.py`: Instancja aplikacji FastAPI i powiązanie `lifespan`.
    - `__main__.py`: Punkt wejścia procesowego.
  - Usunięto przestarzałe parsowanie CLI `get_args` / `argparse` – konfiguracja pobierana jest z obiektów `LLMConfig`, `AudioConfig`, `SatelliteConfig` lub zmiennej `SERVICE_CONFIG`.
  - Ujednolicono struktury klasowe w `__main__.py` (`SatelliteService`, `AudioService`, `LLMService` z konstruktorem `__init__`).

- **Bezportowa Architektura Sidecar Worker Pattern**:
  - Usunięto stawianie surowych serwerów HTTP (Uvicorn) na portach 8001/8002 przez podprocesy.
  - Usługi podrzędne (`satellite`, `audio`, `llm`) **nie otwierają żadnego portu HTTP**.
  - Jedynym otwartym punktem sieciowym w komputerze jest Aplikacja Kliencka (`src/client/internal_proxy.py` na porcie `47831`).
  - Usługi po uruchomieniu subskrybują strumień komend z `/internal/service_commands` i odsyłają wyniki na `/internal/task_event`.

- **Orkiestracja w Kontrolerze**:
  - `src/controller/registry.py` zaktualizowano o pomocniki `get_audio_nodes()`, `get_llm_nodes()`, `get_satellite_nodes()`.
  - Potok czatu w `chat_service.py` realizuje kaskadowe przetwarzanie głosu (`Satelita (WAV) -> STT -> LLM -> TTS -> WS play_audio`).

---

## 2. Aktualny Stan Kodu

- **Struktura Katalogów Usług (`src/client/services/`)**:
  - `src/client/services/satellite/`
  - `src/client/services/audio/`
  - `src/client/services/llm/`
- **Główna Bramka Klienta**:
  - `src/client/internal_proxy.py` (Bramka Gateway HTTP/SSE na porcie `47831`).
  - `src/client/service_bus.py` (Magistrala komend).
  - `src/client/controller_api.py` (Klient WebSocket z Kontrolerem).

---

## 3. Kroki Startowe dla Następnego Agenta

1. Zapoznaj się z plikiem [`docs/MANIFEST.md`](file:///d:/Projekty/Regis/docs/MANIFEST.md) oraz wytycznymi w [`docs/AGENT_GUIDE.md`](file:///d:/Projekty/Regis/docs/AGENT_GUIDE.md).
2. Sprawdź status aktywnych zadań w [`.agents/TASKS.md`](file:///d:/Projekty/Regis/.agents/TASKS.md).
3. Przed dokonaniem jakichkolwiek zmian w kodzie, zawsze skonsultuj plan z użytkownikiem zgodnie z regułami w `AGENTS.md`.
