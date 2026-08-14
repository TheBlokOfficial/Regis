# server

Główny serwer Systemu Regis oparty na FastAPI: REST API v1, strumieniowanie odpowiedzi przez SSE oraz wbudowana konsola Web UI (`src/server/web`). Bramka WebSocket dla architektury rozproszonej jest **planowana** — dziś nie istnieje w kodzie.

Usługa dzieli się na trzy warstwy, w których żadna nie zna z góry implementacji warstwy poniżej (rejestracja jawna w `src/server/main.py`):

| Warstwa | Katalog | Zawartość |
| :--- | :--- | :--- |
| **0 — Kernel** | `src/server/agent/` | `AgentEngine` (pętla ReAct/tool calling), `Gateway`, `MemoryManager`, `ContextBuilder`, `PromptStore`, dostawcy LLM (`backend/`) |
| **1 — Pluginy** | `src/server/plugins/` | `SmartHomePlugin` (urządzenia, grupy, narzędzia LLM) |
| **2 — Integracje** | `src/server/integrations/` | `HomeAssistantIntegration` |

Poza nimi: `network/` (bramka FastAPI i routery REST/SSE), `web/` (SPA), `config.py`, `events.py`, `main.py` (kompozycja aplikacji).

Uruchomienie:
```bash
python -m uv run --package server python -m server.main
```

Pełny opis architektury i przepływów danych: [`docs/manifest.md`](../../docs/manifest.md). Konfiguracja, mapa endpointów i cykl pracy: [`docs/onboarding.md`](../../docs/onboarding.md).
