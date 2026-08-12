# Manifest Projektu Regis

## 1. Cel
System usług rozproszonych komunikujących się po sieci lokalnej.

## 2. Architektura Monorepo i Struktura Katalogów
- **`services/`** – niezależne usługi sieciowe (każda posiada własny kod `src/`, autonomiczną konfigurację `config/` oraz dane `data/`).
  - **`server/`** – serwer centralny Agent OS (`src/server/agent` - silnik, podsystem `backend/providers`, bramka REST/WebSocket).
- **`packages/`** – wspólne biblioteki i kontrakty sieciowe.
  - **`shared/`** – uniwersalne moduły dzielone między usługami (`ConfigStore`, `EventBus`, logowanie).
- **`docs/`** – dokumentacja architektoniczna i instrukcje deweloperskie.

```text
Regis/
├── docs/             # Dokumentacja projektu (manifest, onboarding)
├── packages/         # Wspólne pakiety (np. shared: ConfigStore, EventBus, logger)
├── services/         # Usługi sieciowe
│   └── server/       # Serwer Agent OS (agent/, backend/providers/, network/)
├── pyproject.toml    # Konfiguracja uv workspace
└── README.md         # Wprowadzenie do projektu
```

## 3. Stos Technologiczny i Zasady
- **Język**: Python 3.11+
- **Zarządzanie monorepo i zależnościami**: `uv` (`uv workspace`)
- **Komunikacja**: WebSockets & REST (FastAPI + Uvicorn)
- **Model zdarzeniowy**: Asynchroniczna magistrala zdarzeń (`EventBus` oparta o `asyncio`)
- **Typowanie**: Obowiązkowe adnotacje typów (Strict Type Hints)

