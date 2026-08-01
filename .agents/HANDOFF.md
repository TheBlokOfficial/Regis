# Przekazanie Sesji (Handoff)

## Ostatnia Sesja: Modularyzacja Web UI (app.js → ES Modules)

### Co zostało zrobione w tej sesji:

1. **Analiza i diagnoza monolitu `app.js`** (448 linii):
   - Zidentyfikowano 5 oddzielnych odpowiedzialności sklejonych w jednym pliku: globalny stan, warstwa sieciowa, renderowanie DOM, obsługa zdarzeń SSE, sterowanie węzłami.

2. **Pełny refactoring `src/controller/web/` na natywne ES Modules** (bez bundlera):
   - `utils.js` [NEW] — czyste funkcje pomocnicze: `fmtUptime`, `fmtTime`, `escHtml`, `truncate`. Zero zależności.
   - `state.js` [NEW] — centralny store: `workers`, `satellites` + funkcje mutacji (`upsertWorker`, `setWorkerStatus`, `upsertSatellite`, `removeSatellite`, `workerCount`, `satelliteCount`). Zero zależności.
   - `renderer.js` [NEW] — pełna warstwa DOM: `initClock`, `updateHAStatus`, `renderWorkerCard`, `markWorkerOffline`, `renderSatelliteCard`, `markSatelliteOffline`, `updateSatelliteVAD`, `appendLog`. Importuje: `state.js`, `utils.js`. Inline `onclick` zastąpiony `addEventListener`.
   - `events.js` [NEW] — obsługa zdarzeń SSE: `handleEvent` z switchem 8 przypadków. Importuje: `state.js`, `renderer.js`, `utils.js`.
   - `api.js` [NEW] — warstwa sieciowa: `init`, `connectSSE`, `sendNodeCommand`, prywatna `_startUptimePoller`. Importuje: `state.js`, `renderer.js`, `events.js`, `utils.js`.
   - `app.js` [MODIFY] — z 448 linii do ~20 linii orchestratora. Eksponuje `window.sendNodeCommand` (wymagane dla event listenerów kart węzłów bez cyklicznych importów).
   - `index.html` [MODIFY] — jedyna zmiana: `<script type="module" src="/app.js">`.
   - `style.css` — bez zmian.

### Kluczowe decyzje architektoniczne:

- **Natywne ES Modules** — zero bundlera, zero nowych zależności. FastAPI StaticFiles serwuje `.js` z poprawnym MIME type automatycznie.
- **`window.sendNodeCommand`** — jedyne globalne powiązanie. Wymagane bo `renderer.js` nie może importować z `api.js` (cykl: `api → renderer → api`). Zarejestrowane w `app.js` przed jakimkolwiek renderowaniem.
- **Graf zależności bez cykli**: `utils`, `state` (brak importów) → `renderer` → `events` → `api` → `app`.
- **Prywatne funkcje modułu** — konwencja `_` (np. `_startUptimePoller`, `_commandToBtnId`).

---

### Wskazówki startowe dla następnego agenta:

1. **ZADANIE:** Implementacja **Fazy 3 Web UI** (zgodnie z `docs/web_ui_rfc.md` §6.2):
   - Satelita pushuje zdarzenia do Kontrolera (`POST /api/satellite/event`).
   - Wymaga modyfikacji `src/node/satellite.py` (dodanie wysyłania eventów VAD/WakeWord do Kontrolera) i dodania endpointu `POST /api/satellite/event` w `src/controller/routers/ui.py`.
   - Aktualnie satelita wysyła eventy tylko do lokalnego `service.py` (port 8099) — nie trafiają do centralnego EventBusa.

2. **ZADANIE:** Implementacja **Fazy 4 Web UI** (zgodnie z `docs/web_ui_rfc.md` §6.3):
   - Akcja `open_dashboard()` w `src/node/service.py` otwiera `webbrowser.open(controller_url)` zamiast terminala.
   - Po weryfikacji: usunięcie `src/node/dashboard.py`.

3. **Weryfikacja modularyzacji** — przed kolejnymi zmianami w web UI: wdrożyć na RPi5 przez `tools/build_controller.py` i sprawdzić brak błędów w konsoli przeglądarki. FastAPI StaticFiles powinien serwować nowe pliki `.js` bez zmian w konfiguracji.

4. **Stan kart węzłów** — status inicjalizowany z `/api/status`, aktualizowany przez SSE. Gdy Faza 3 będzie wdrożona, statusy VAD/WakeWord w kartach satelit zaczną działać w czasie rzeczywistym.
