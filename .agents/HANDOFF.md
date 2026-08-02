# Regis Project Handoff

## Ostatnia Sesja (Zrealizowano)

**Refaktoryzacja Architektury Modułu Node (Async & BaseSubservice)**

Przeprowadzono gruntowną reorganizację i unowocześnienie modułu `src/node/`:

1. **Usunięcie `node.py` (Likwidacja *God Object*)**: Usunięto przerośniętą klasę `WorkerNode`. Usługa `worker.py` ładuje silniki bezpośrednio w cyklu życia (`lifespan`) i orkiestruje potok (STT -> LLM -> TTS) natywnie w endpointach HTTP.
2. **Czysta Asynchroniczność (`httpx.AsyncClient`)**: Zastąpiono `requests`, wątki (`threading.Thread`) oraz `asyncio.Queue` w backendzie Ollamy (`ollama.py`) i `LLMEngine` na natywne asynchroniczne generatory (`AsyncGenerator`). Endpointy `/v1/chat/stream` oraz `/v1/chat/audio_stream` używają teraz `StreamingResponse` bezpośrednio z async generatorów.
3. **Przekazywanie Konfiguracji przez CLI (Likwidacja Split-Brain)**: Wdrożono `argparse` w `worker.py` i `satellite.py`. Menedżer procesów przekazuje parametry uruchomieniowe (np. `--model`, `--port`, `--room`) bezpośrednio przy starcie procesów.
4. **Obiektowe Zarządzanie Procesami (`BaseSubservice`)**:
   - Stworzono klasę bazową `BaseSubservice` w `process_manager.py`, która hermetyzuje obsługę systemową (tworzenie logów, izolacja `Job Object` w Windows, `CREATE_NO_WINDOW`, weryfikacja stanu procesów).
   - Zbudowano konkretne klasy `WorkerSubservice` i `SatelliteSubservice` zintegrowane w dynamicznym słowniku `SERVICES: dict[str, BaseSubservice]`.
   - Zlikwidowano hardkodowane funkcje (m.in. powtarzalne `stop_worker()`, `stop_satellite()`). Funkcja `quit_all()` w `service.py` używa uniwersalnego `stop_all_services()`.
   - `controller_client.py` generuje rejestrację oraz odpowiedź statusową dla WebSocketu w sposób dynamiczny z rejestru `SERVICES`.

## Aktualny Stan Kodu

- **Możliwości Modułu Node**: W pełni zmigrowany na `httpx.AsyncClient` i architekturę obiektową `BaseSubservice`.
- **Dobre praktyki**: Brak "split-brain" w konfiguracji, czyste przekazywanie CLI args z Kontrolera.
- **Testy**: **34/34 testy przechodzą** (`pytest`).
- **Zero cross-importów**: Utrzymana bezwzględna izolacja między `node` i `controller`.

## Zasada Architektury (do przestrzegania)

> Węzeł (`node`) jest biernym wykonawcą sterowanym w 100% przez Kontroler. Wszelkie pod-usługi uruchamiane przez Węzeł dziedziczą po `BaseSubservice` i są dodawane do rejestru `SERVICES` w `process_manager.py`.

## Kroki Startowe dla Nowego Agenta

1. Przeczytaj `docs/MANIFEST.md` i `docs/AGENT_GUIDE.md`.
2. Uruchom `pytest` w katalogu głównym — powinno przejść 34/34.
3. Przejdź do `.agents/TASKS.md` po następne zadanie.
