# HANDOFF: Stan Projektu Regis

## 1. Wykonane Prace w Ostatniej Sesji (2026-08-07)

- **Uproszczenie Maszyny Stanów Satelity i Eliminacja Podwójnej Warstwy Stanów**:
  - Usunięto całkowicie podwójną maszynę stanów (`SatelliteInteractionState` i plik `src/client/services/satellite/states.py`).
  - Stany domenowe (`WAKEWORD`, `LISTENING`, `STREAMING`, `SPEAKING`, `PROCESSING`) zostały zastąpione zwykłymi zdarzeniami emitowanymi na magistrali zdarzeń (`EventBus`).
  - Satelita komunikuje do Kontrolera wyłącznie jednolity stan infrastrukturalny `ServiceState` (`READY` / `BUSY`), eliminując race conditions oraz konieczność istnienia wyjątków dla Satelity.

- **Refaktoryzacja i Czyszczenie Protokołu Sieciowego (`src/protocol/schemas.py`)**:
  - Przeniesiono klasę `CloudProviderConfig` z protokołu sieciowego do modułu Kontrolera ([`src/controller/routers/cloud_providers.py`](file:///d:/Projekty/Regis/src/controller/routers/cloud_providers.py)), zamykając wyciek wewnętrznej konfiguracji Kontrolera do Klientów.
  - Zmieniono nazwę `WSSatelliteEvent` na uniwersalne `WSClientEvent` z zachowaniem aliasu wstecznej kompatybilności.
  - Usunięto nieużywane już schematy rejestracyjne i metody przeliczające.

- **Eliminacja Długu Ewolucyjnego i Czyszczenie Aplikacji Klienckiej (`src/client`)**:
  - Usunięto całkowicie nieużywany, martwy folder [`src/client/legacy/`](file:///d:/Projekty/Regis/src/client/legacy/) zawierający stare interfejsy TUI (wizard, monitor).
  - Ujednolicono terminologię z czasów "Węzłów" (`Node`) na `Client` / `client_id` w plikach [`config.py`](file:///d:/Projekty/Regis/src/client/config.py), [`tray.py`](file:///d:/Projekty/Regis/src/client/tray.py), [`controller_api.py`](file:///d:/Projekty/Regis/src/client/controller_api.py), [`internal_proxy.py`](file:///d:/Projekty/Regis/src/client/internal_proxy.py) oraz [`client_registry.py`](file:///d:/Projekty/Regis/src/client/network/client_registry.py).
  - Zapewniono automatyczną migrację starych kluczy konfiguracyjnych (`node_id`, `instance_name`) do uniwersalnego `client_id`.

- **Notatka Projektowa (RFC)**:
  - Spisano koncepcję inwalidacji kontekstu LLM podczas napływu nowych zdarzeń w trakcie przetwarzania w pliku [`docs/context_invalidation_rfc.md`](file:///d:/Projekty/Regis/docs/context_invalidation_rfc.md).

---

## 2. Aktualny Stan Kodu

- **Klient (`src/client/`)**: W 100% zrefaktoryzowany, wyczyszczony z martwego kodu i przetestowany pod kątem kompilacji.
- **Protokół (`src/protocol/schemas.py`)**: Czysty, 100% hermetyczny kontrakt sieciowy pomiędzy Klientem a Kontrolerem.
- **Satelita (`src/client/services/satellite/`)**: Działa w oparciu o architekturę jednolicie pasywną (READY/BUSY) ze zdarzeniami emisyjnymi dla UI.

---

## 3. Kroki Startowe dla Następnego Agenta

1. Obowiązkowo zapoznaj się z [`docs/MANIFEST.md`](file:///d:/Projekty/Regis/docs/MANIFEST.md) oraz [`docs/AGENT_GUIDE.md`](file:///d:/Projekty/Regis/docs/AGENT_GUIDE.md).
2. Sprawdź status zadań w [`.agents/TASKS.md`](file:///d:/Projekty/Regis/.agents/TASKS.md).
3. Rozpocznij refaktoryzację **Kontrolera** (`src/controller`), skupiając się na oczyszczeniu routerów, rejestru oraz optymalizacji logiki orkiestracji.
