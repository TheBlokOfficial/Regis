# Przekazanie Sesji (Handoff)

## Ostatnia Sesja: Projektowanie Reaktywnego Web UI — RFC i Decyzje Architektoniczne

### Co zostało zrobione w tej sesji:

1. **Decyzja architektoniczna: Reaktywny Web UI zamiast terminal CLI**
   - Podjęto decyzję o zastąpieniu synchronicznego dashboardu CLI (`src/node/dashboard.py`) reaktywnym panelem webowym.
   - Motywacja: terminal CLI jest synchroniczny (polling), wymaga otwartego okna konsoli i nie pokazuje zdarzeń w czasie rzeczywistym.

2. **Decyzja: Backend Web UI = Kontroler**
   - Panel webowy jest serwowany przez Kontroler (RPi5 / Minisforum), nie przez węzeł Windows.
   - Uzasadnienie: Kontroler to jedyne źródło prawdy (MANIFEST §3.1) i ma dostęp do stanu całego systemu.
   - Węzeł Windows pozostaje cichą usługą w tle (System Tray) — provider Worker LLM + Satelita Audio.

3. **Decyzja: Protokół SSE (Server-Sent Events)**
   - Reaktywność przez SSE — natywne dla przeglądarki (`EventSource` API).
   - Kontroler już używa SSE w `routers/chat.py` — spójny z istniejącym kodem.

4. **Decyzja: Sterowanie węzłem przez Kontroler jako proxy HTTP**
   - Kliknięcie w Web UI → żądanie do Kontrolera → Kontroler wysyła HTTP do `node.service` (port 8099) → wynik przez SSE do przeglądarki.
   - Węzeł nie jest eksponowany bezpośrednio do użytkownika.

5. **Stworzono dokument RFC:** `docs/web_ui_rfc.md`
   - Kompletny plan implementacji z decyzjami architektonicznymi, schematem systemu, projektem EventBus, endpointami API, layoutem Web UI i 4 fazami realizacji.

---

### Kluczowe decyzje architektoniczne podjęte w tej sesji:

- **Web UI na Kontrolerze** — panel centralny dla całego systemu, dostępny z każdego urządzenia w sieci domowej.
- **SSE** — protokół reaktywności. Brak WebSocket (niepotrzebna dwukierunkowość).
- **Vanilla JS + HTML/CSS** — zero frameworków frontendowych, zero procesu budowania.
- **`dashboard.py` do usunięcia** — po wdrożeniu Web UI staje się zbędny.
- **System Tray** — akcja "Otwórz Dashboard" będzie otwierać przeglądarkę pod adresem Kontrolera (`webbrowser.open()`).
- **Satelita pushuje zdarzenia do Kontrolera** (Podejście A z RFC §6.2) — zmiana w `satellite.py`.

---

### Wskazówki startowe dla następnego agenta:

1. **ZADANIE:** Implementacja Reaktywnego Web UI zgodnie z `docs/web_ui_rfc.md`.
2. **Zacznij od Fazy 1** (RFC §8): stworzenie `src/controller/event_bus.py` + nowy router `src/controller/routers/ui.py` z endpointami `/api/events`, `/api/status`, `/api/node/{id}/command`. Zarejestruj router w `app.py` PRZED montowaniem StaticFiles.
3. **Faza 2** po weryfikacji Fazy 1: Web UI w `src/controller/web/` (index.html, style.css, app.js).
4. **Fazy 3 i 4** mogą być realizowane równolegle lub po Fazie 2: satelita pushuje zdarzenia do Kontrolera + integracja System Tray.
5. **Styl CSS:** ascetyczny — ciemne tło (`#0f0f0f`), biały tekst, szary dla metadanych. Zero cyan/magenta/yellow. Szczegóły w RFC §7.3.
6. **Uwaga krytyczna przy montowaniu StaticFiles:** Router `/api/...` musi być zarejestrowany w `app.py` PRZED `app.mount("/", StaticFiles(...))` — StaticFiles jest catch-all i przesłoni API jeśli dodany wcześniej.
7. Realizuj **fazę po fazie** z weryfikacją między nimi — nie "za jednym strzałem".
