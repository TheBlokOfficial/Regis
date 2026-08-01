# RFC: Reaktywny Web UI dla Regisa

**Data:** 2026-08-01  
**Status:** Do realizacji  
**Autor koncepcji:** Użytkownik + sesja architektoniczna 2026-08-01

---

## 1. Motywacja i Cel

Aktualny terminal CLI (`src/node/dashboard.py`) jest synchroniczny i blokujący — każda akcja wymaga aktywnej interakcji. Nie informuje o zdarzeniach w czasie rzeczywistym (np. aktywacja VAD/WakeWord, zmiana stanu połączenia z Kontrolerem). Konieczność utrzymywania otwartego okna konsoli jest uciążliwa i sprzeczna z filozofią „Nie Przeszkadzaj" zapisaną w MANIFEST.md.

**Cel:** Zastąpienie synchronicznego dashboardu CLI reaktywnym Web UI obsługiwanym przez Kontroler, przy zachowaniu lekkich usług w tle na węzłach.

---

## 2. Decyzje Architektoniczne (Rozstrzygnięte)

| Pytanie | Decyzja | Uzasadnienie |
|---|---|---|
| Gdzie siedzi backend Web UI? | **Kontroler** (RPi5 / Minisforum) | Kontroler to jedyne źródło prawdy (MANIFEST §3.1). Dashboard operuje na danych z całego systemu, nie tylko jednego węzła. |
| Protokół reaktywności? | **SSE (Server-Sent Events)** | Natywne dla przeglądarki (`EventSource` API). Jednokierunkowy strumień push od serwera — idealny dla monitoringu stanu. Brak narzutu WebSocket. Kontroler już używa SSE w `routers/chat.py`. |
| Co robi węzeł Windows po zmianie? | **Wyłącznie provider + REST API sterowania** | `node.service` uruchamia Worker LLM i Satelitę, rejestruje się w Kontrolerze i udostępnia lokalne REST API (port 8099) do zdalnego sterowania przez Kontroler. Terminal dashboard (`dashboard.py`) staje się zbędny. |
| Jak sterujemy węzłem z Web UI? | **Kontroler jako proxy HTTP** | Kliknięcie w Web UI → żądanie do Kontrolera → Kontroler wysyła HTTP do `node.service` węzła → wynik wraca przez SSE do przeglądarki. Węzeł nigdy nie jest eksponowany bezpośrednio. |
| Technologia frontendu? | **Czysty HTML + Vanilla JS + CSS** | Zero frameworków, zero procesu budowania. Serwowane jako pliki statyczne bezpośrednio z FastAPI (`StaticFiles`). Spójna z filozofią lekkości projektu. |

---

## 3. Architektura Systemu po Wdrożeniu

```
┌─────────────────────────────────────────────────┐
│               KONTROLER (RPi5 / Minisforum)     │
│                                                 │
│  FastAPI                                        │
│   ├── /              → serwuje Web UI (HTML)    │
│   ├── /api/events    → SSE: strumień zdarzeń    │
│   ├── /api/status    → REST: stan systemu       │
│   └── /api/node/{id}/command → proxy do węzła  │
│                                                 │
│  EventBus (nowy moduł controller/event_bus.py)  │
│   └── publikuje: rejestracje, heartbeaty,       │
│       routing decyzji, zdarzenia satelit        │
└─────────────────────────────────────────────────┘
         ↑ SSE / REST (HTTP)           ↑
         │                             │
  ┌──────────────┐             ┌──────────────┐
  │  Przeglądarka│             │ node.service │
  │  (Web UI)    │             │  (Windows PC)│
  │              │             │              │
  │  EventSource │             │  port 8099   │
  │  + fetch()   │             │  REST API    │
  └──────────────┘             │   /status    │
                               │   /worker/.. │
                               │   /satellite/│
                               └──────────────┘
```

---

## 4. Co Znika, Co Zostaje

### Znika (do usunięcia po wdrożeniu Web UI):
- `src/node/dashboard.py` — synchroniczny terminal CLI. Zbędny.
- Akcja *„Otwórz panel kontrolny"* w `service.py` otwierająca terminal CLI — zostaje zastąpiona akcją otwierającą przeglądarkę pod adresem Kontrolera.
- Zależność od `questionary` w dashboard (jeśli nie jest używana gdzie indziej).

### Zostaje bez zmian:
- `src/node/service.py` — system tray + zarządzanie procesami Worker i Satelita. Rozszerzyć o REST API sterowania (szczegóły w §6).
- `src/node/worker.py` — logika Workera LLM.
- `src/node/satellite.py` — logika Satelity audio.
- `src/controller/routers/chat.py` — strumień SSE konwersacji głosowych (używać go jako źródła eventów konwersacji dla Web UI).
- Cały Rejestr Encji (`registry.py`) — stanowi fundament Web UI.

---

## 5. Plan Wdrożenia — Backend (Kontroler)

### 5.1 Nowy moduł: `src/controller/event_bus.py`

Szyna zdarzeń wewnątrz Kontrolera. Analogiczna do szyny w `node/service.py`, ale operuje na zdarzeniach całego systemu.

**Typy zdarzeń publikowanych przez szynę:**

| Typ zdarzenia | Źródło | Dane |
|---|---|---|
| `worker_registered` | Router `/v1/workers/register` | `{id, host, port, model_name, tier}` |
| `worker_unregistered` | Heartbeat loop | `{id}` |
| `satellite_registered` | Router `/v1/satellites/register` | `{id, room, type, capabilities}` |
| `satellite_unregistered` | Heartbeat loop (lub brak odnawiania) | `{id}` |
| `satellite_event` | Węzeł publikuje event Satelity (VAD, WakeWord) | `{satellite_id, type, data}` |
| `routing_decision` | Router chat przy wyborze węzła | `{session_id, worker_id, model_name, tier}` |
| `conversation_turn` | Po zakończeniu tury (bez śladu ReAct) | `{satellite_id, user_text, assistant_text, worker_id, duration_s}` |
| `node_command_result` | Po wykonaniu komendy na węźle | `{node_id, command, success}` |

**Implementacja (Python):**

```python
# src/controller/event_bus.py
import asyncio
import json
from collections import deque

_history: deque = deque(maxlen=500)
_subscribers: list[asyncio.Queue] = []

async def publish(event: dict) -> None:
    _history.append(event)
    for q in list(_subscribers):
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            pass

async def subscribe() -> tuple[asyncio.Queue, list[dict]]:
    """Zwraca nową kolejkę SSE i historię do odtworzenia dla nowego klienta."""
    q: asyncio.Queue = asyncio.Queue(maxsize=500)
    _subscribers.append(q)
    return q, list(_history)

def unsubscribe(q: asyncio.Queue) -> None:
    try:
        _subscribers.remove(q)
    except ValueError:
        pass
```

### 5.2 Nowy router: `src/controller/routers/ui.py`

Obsługuje trzy endpointy dla Web UI:

```
GET  /             → serwuje index.html (plik statyczny Web UI)
GET  /api/events   → SSE: strumieniuje zdarzenia z EventBus
GET  /api/status   → REST: snapshot stanu systemu (rejestry, ustawienia)
POST /api/node/{node_id}/command  → proxy komendy do węzła
```

**Endpoint `/api/events` (SSE):**

```python
@router_ui.get("/api/events")
async def events_stream(request: Request):
    async def generator():
        q, history = await event_bus.subscribe()
        try:
            # Odtwórz historię dla nowego klienta
            for event in history:
                yield f"data: {json.dumps(event)}\n\n"
            # Strumieniuj nowe zdarzenia
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"  # Utrzymuje połączenie
        finally:
            event_bus.unsubscribe(q)
    return StreamingResponse(generator(), media_type="text/event-stream")
```

**Endpoint `/api/status` (REST):**

Zwraca pełny snapshot stanu systemu:
```json
{
  "workers": [
    {"id": "windows-pc", "host": "192.168.0.10", "port": 8001,
     "model_name": "qwen2.5:9b", "tier": "regis", "status": "online"}
  ],
  "satellites": [
    {"id": "windows-pc-sat", "room": "gabinet", "type": "desktop",
     "capabilities": ["audio_in", "audio_out"]}
  ],
  "controller": {
    "version": "...",
    "uptime_s": 3600,
    "ha_status": "online"
  }
}
```

**Endpoint `/api/node/{node_id}/command` (POST):**

Proxy komend do węzła. Kontroler odnajduje adres węzła w `worker_registry` lub `satellite_registry`, przekazuje komendę przez HTTP i zwraca wynik. Dostępne komendy:

| Komenda | Opis |
|---|---|
| `worker_start` | Uruchomienie lokalnego Workera LLM na węźle |
| `worker_stop` | Zatrzymanie lokalnego Workera LLM |
| `satellite_start` | Uruchomienie Satelity Audio |
| `satellite_stop` | Zatrzymanie Satelity Audio |
| `status` | Pobranie aktualnego stanu usługi węzła |

### 5.3 Pliki statyczne Web UI

Katalog: `src/controller/web/`

```
src/controller/web/
├── index.html      ← Główna strona panelu
├── style.css       ← Stylowanie
└── app.js          ← Logika reaktywna (EventSource + fetch)
```

Montowanie w `app.py`:
```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="controller/web", html=True), name="web")
```

> **Ważne:** Router `/api/...` musi być zarejestrowany **przed** montowaniem `StaticFiles`, ponieważ `StaticFiles` jest catch-all i przesłoni dynamiczne endpointy jeśli zostanie dodany wcześniej.

---

## 6. Plan Wdrożenia — Backend (Węzeł Windows)

`src/node/service.py` wymaga rozszerzenia REST API o endpointy sterowania zdalnego, wywoływane przez Kontroler (jako proxy).

### 6.1 Nowe endpointy w `_ServiceHandler` (port 8099)

Obecny stan: węzeł ma `/worker/toggle` i `/satellite/toggle`. To jest wystarczające dla sterowania przez Kontroler — **żadnych zmian nie potrzeba w API węzła** jeśli Kontroler przetłumaczy komendy `worker_start/stop` i `satellite_start/stop` na odpowiednie wywołania toggle.

Alternatywnie, dla większej precyzji (start i stop jako oddzielne endpointy zamiast toggle):

```
POST /worker/start      → uruchamia Worker jeśli nie działa
POST /worker/stop       → zatrzymuje Worker jeśli działa
POST /satellite/start   → uruchamia Satelitę jeśli nie działa
POST /satellite/stop    → zatrzymuje Satelitę jeśli działa
GET  /status            → {worker: "running"|"stopped", satellite: "running"|"stopped"}
```

> **Uwaga dla agenta:** Sprawdź czy toggle vs. osobne start/stop jest potrzebne. Jeśli Kontroler zna aktualny stan węzła (z ostatniego heartbeatu/`/status`), może samodzielnie zdecydować czy wywołać `/worker/start` czy `/worker/stop` bez potrzeby toggle. Preferuj jawne komendy.

### 6.2 Satelita publikuje zdarzenia do Kontrolera

Aktualnie: Satelita publikuje zdarzenia (VAD, WakeWord) do lokalnej szyny w `service.py` przez `POST /satellite/event`. Monitor głosowy (`monitor_voice.py`) subskrybuje je przez SSE na `GET /satellite/events`.

Po wdrożeniu Web UI: Kontroler musi znać zdarzenia Satelity aby wyświetlać je w centralnym panelu. Dwa podejścia:

**Podejście A (Rekomendowane): Satelita → Kontroler (push)**  
Satelita wysyła zdarzenia bezpośrednio do Kontrolera (`POST /api/satellite/event`). Kontroler umieszcza je na swojej szynie EventBus. Prosto i bez pośredników.

**Podejście B: Kontroler odpytuje węzeł (pull)**  
Kontroler subskrybuje SSE z węzła (`GET http://[node]:8099/satellite/events`). Bardziej złożone, ale nie wymaga zmian po stronie Satelity.

Podejście A jest czystsze i zgodne z filozofią „Kontroler jako centrum" — wymaga drobnej zmiany w `satellite.py` (dodanie `server_url` jako dodatkowego odbiorcy eventów).

### 6.3 Ikona System Tray — nowa akcja

W `service.py`, akcja *„Otwórz panel kontrolny"* przestaje otwierać terminal CLI i zamiast tego otwiera przeglądarkę pod adresem Kontrolera:

```python
import webbrowser
def open_web_dashboard():
    settings = get_settings()
    controller_url = settings.get("server_url", "http://192.168.0.50:8000")
    webbrowser.open(controller_url)
```

---

## 7. Plan Wdrożenia — Frontend (Web UI)

### 7.1 Layout i sekcje panelu

```
┌─────────────────────────────────────────────────────┐
│  REGIS — Panel Kontrolny          [czas systemowy]  │
├─────────────────────────────────────────────────────┤
│  Stan Systemu                                       │
│   Home Assistant: ONLINE   Kontroler: v1.x  3600s   │
├──────────────────────┬──────────────────────────────┤
│  Węzły robocze       │  Satelity                    │
│                      │                              │
│  [windows-pc]        │  [windows-pc-sat]            │
│  Worker: ONLINE      │  Pomieszczenie: gabinet      │
│  qwen2.5:9b (regis)  │  VAD: [cisza]                │
│  [Zatrzymaj] [swap]  │  WakeWord: aktywny           │
│                      │  [Zatrzymaj]                 │
├──────────────────────┴──────────────────────────────┤
│  Dziennik zdarzeń na żywo                           │
│                                                     │
│  12:47:30  [windows-pc-sat]  WakeWord wykryty       │
│  12:47:31  [routing]  → windows-pc  qwen2.5:9b      │
│  12:47:34  [Ty] włącz światło w salonie             │
│  12:47:37  [Regis] Gotowe. (3.1s, 1 narzędzie)     │
│  12:47:37  [windows-pc-sat]  cisza                  │
└─────────────────────────────────────────────────────┘
```

### 7.2 Logika reaktywna (`app.js`)

```javascript
// Połączenie SSE — jeden raz przy ładowaniu strony
const es = new EventSource('/api/events');

es.onmessage = (e) => {
    const event = JSON.parse(e.data);
    handleEvent(event);
};

// Pierwsza inicjalizacja — pobierz snapshot stanu
async function init() {
    const status = await fetch('/api/status').then(r => r.json());
    renderWorkers(status.workers);
    renderSatellites(status.satellites);
    renderControllerInfo(status.controller);
}

// Obsługa zdarzeń — aktualizacja tylko zmienionych elementów DOM
function handleEvent(event) {
    switch (event.type) {
        case 'worker_registered':   updateWorkerCard(event, 'online'); break;
        case 'worker_unregistered': updateWorkerCard(event, 'offline'); break;
        case 'satellite_event':     updateSatelliteVAD(event); break;
        case 'conversation_turn':   appendToLog(event); break;
        case 'routing_decision':    appendToLog(event); break;
        // ...
    }
}

// Sterowanie węzłem przez Kontroler (proxy)
async function sendNodeCommand(nodeId, command) {
    await fetch(`/api/node/${nodeId}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command })
    });
}
```

### 7.3 Estetyka i styl

Zgodnie z filozofią ascetyczności projektu (MANIFEST.md, AGENTS.md):
- **Typografia:** Czysty, monospacowany lub sans-serif font (np. IBM Plex Mono / Inter).
- **Kolory:** Ciemne tło (`#0f0f0f` lub `#111`), biały tekst (`#e0e0e0`), szary (`#555`) dla metadanych. Czerwony wyłącznie dla błędów, zielony dla stanu ONLINE. Zero jaskrawego cyan/magenta/yellow jako dekoracji.
- **Układ:** Minimalistyczny grid. Żadnych masywnych ramek ani gradientowych boksów.
- **Animacje:** Tylko subtelne — delikatne fade-in dla nowych wpisów w dzienniku.

---

## 8. Kolejność Realizacji (Fazy)

### Faza 1 — Backend Kontrolera (fundament)
1. Stworzenie `src/controller/event_bus.py`.
2. Wpięcie EventBus do istniejących routerów (workers, satellites, chat).
3. Stworzenie `src/controller/routers/ui.py` z endpointami `/api/events`, `/api/status`, `/api/node/{id}/command`.
4. Zarejestrowanie routera `ui` w `app.py` i zamontowanie `StaticFiles`.

### Faza 2 — Frontend (Web UI)
1. Stworzenie `src/controller/web/index.html`, `style.css`, `app.js`.
2. Implementacja pełnej logiki reaktywnej (EventSource + fetch + renderowanie kart).
3. Implementacja sterowania węzłami z poziomu Web UI.

### Faza 3 — Satelita pushuje zdarzenia do Kontrolera
1. Modyfikacja `src/node/satellite.py` — publikowanie zdarzeń do Kontrolera (Podejście A z §6.2).
2. Dodanie endpointu `POST /api/satellite/event` w routerze UI Kontrolera.

### Faza 4 — Integracja z System Tray
1. Modyfikacja `src/node/service.py` — akcja *„Otwórz Dashboard"* otwiera przeglądarkę zamiast terminala.
2. Usunięcie `src/node/dashboard.py` po weryfikacji że nic nie zależy od jego importów.

> **Uwaga:** Fazy 1 i 2 są niezależne od węzła Windows i mogą być realizowane wyłącznie na RPi5/Minisforum. Fazy 3 i 4 dotyczą węzła Windows i mogą być realizowane równolegle lub po Fazie 2.

---

## 9. Zależności i Nowe Paczki

### Kontroler
- **Brak nowych zależności Pythona.** FastAPI ma wbudowaną obsługę `StreamingResponse` i `StaticFiles` (przez `aiofiles` — już zapewne zainstalowane).
- Jeśli `aiofiles` nie jest w `requirements.txt`: `pip install aiofiles`.

### Węzeł Windows
- **Brak nowych zależności.** Zmiana `open_dashboard()` na `webbrowser.open()` używa biblioteki standardowej.

---

## 10. Co to Zmienia dla Użytkownika

| Przed | Po |
|---|---|
| Konieczność trzymania otwartego okna terminala CLI na Windowsie | Węzeł działa cicho w tle, terminal niepotrzebny |
| Dashboard CLI odpytuje serwer co sekundę (polling) | Przeglądarka subskrybuje zdarzenia — natychmiastowe aktualizacje |
| Dostęp do stanu systemu tylko z komputera z zainstalowanym Regisem | Dostęp z każdego urządzenia w sieci domowej (PC, telefon, tablet) |
| Brak podglądu zdarzeń audio (VAD, WakeWord) w czasie rzeczywistym | Dziennik na żywo pokazuje cały pipeline: VAD → WakeWord → routing → odpowiedź |
| Sterowanie workerem tylko przez menu CLI | Sterowanie jednym kliknięciem z poziomu przeglądarki |

---

## 11. Otwarte Kwestie dla Przyszłych Sesji

1. **Autentykacja Web UI:** Czy panel powinien wymagać hasła dostępu? Na etapie sieci domowej (localhost / LAN) można to pominąć, ale warto rozważyć prosty token w nagłówku (Bearer) jeśli kontroler będzie dostępny przez port forward w przyszłości.
2. **Swap modelu Workera z Web UI:** Funkcja przełączania modelu między profilem Butler/Regis (opisana w TASKS.md jako `WORKER PROFILE SWAP`) naturalnie wpisuje się w Web UI jako dodatkowy przycisk w karcie węzła. Realizować razem czy oddzielnie?
3. **Mobile-first layout:** Panel powinien być użyteczny na telefonie (szczególnie przy sterowaniu przez sieć domową). Czy priorytetować responsive layout od razu, czy dodać w osobnym kroku?
