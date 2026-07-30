# Plan Implementacji: Monitor Konwersacji i Refaktoryzacja Traya

## Kontekst i cel

Projekt ma dwa odrębne problemy wymagające naprawy:

1. **Brak transparentności przepływu informacji** — podczas rozmowy z systemem nie wiadomo który węzeł obsługuje żądanie, jakim modelem, jak długo trwa inferencja. Narzędzie `dev_chat()` w `chat.py` jest ślepe na te informacje, bo warstwa `RemoteClient` je odrzuca.

2. **UX i nazewnictwo** — menu CLI i dashboardu używają roboczych, technicznych etykiet (`"Transparentny Panel (Podgląd LLM)"`, `"Chat z serwerem (Dev)"`). Tray ma za dużo opcji i miesza odpowiedzialności usługi z zarządzaniem nią.

Plan jest podzielony na dwa etapy. **Etap 1** jest izolowany i bezpieczny — zmiany w 5 plikach, zero nowych zależności. **Etap 2** to większa zmiana architektoniczna — nowy serwer HTTP w trayu i przepisanie dashboardu.

> [!IMPORTANT]
> **Zasada dla agenta wykonującego:** Nie implementuj niczego poza zakresem etapu który realizujesz. Nie "naprawiaj przy okazji" rzeczy które nie są w liście zmian. Nie dodawaj emoji. Nie używaj `cyan`, `yellow`, `magenta` jako kolorów dekoracyjnych — tylko `dim` dla metadanych, `bold white` dla nagłówków, `red` dla błędów, `green` dla sukcesów.

---

# ETAP 1: Monitor Konwersacji

## Co to jest i jak ma działać

"Monitor" to przepisany moduł `chat.py`. Zamiast prostego czatu, jest to **narzędzie obserwacyjne** — wyświetla pełny przepływ zdarzeń między użytkownikiem, Kontrolerem i Węzłem. Działa w dwóch trybach przełączanych komendą `/verbose` wpisaną w trakcie sesji.

**Tryb normalny** (domyślny) — czytelny jak rozmowa:
```
─────────────────────────────────────────────────────────
[20:47:31] Ty: włącz światło w salonie

Regis: Gotowe, włączyłem światło w salonie.
  ·  windows-pc-node  qwen2.5:14b-instruct  1 narzędzie  3.1s
─────────────────────────────────────────────────────────
```

**Tryb verbose** — pełny przepływ zdarzeń:
```
─────────────────────────────────────────────────────────
[20:47:31] Ty: włącz światło w salonie
  → windows-pc-node  qwen2.5:14b-instruct  tier: regis

  <myśl>
  Użytkownik prosi o włączenie światła w salonie.
  Sprawdzam dostępne urządzenia...
  </myśl>

  [narzędzie] light.turn_on
    wejście: {"entity_id": "light.salon_ceiling"}
    wynik:   {"result": "ok"}

Regis: Gotowe, włączyłem światło w salonie.
  ·  3.1s
─────────────────────────────────────────────────────────
```

---

## 1.1 Zmiana w `controller/router.py`

**Dlaczego:** Kontroler jest proxy — wybiera węzeł i przekazuje jego odpowiedź, ale nigdy nie informuje klienta *który węzeł wybrał*. Bez tej informacji Monitor nie wie z kim rozmawia. Rozwiązanie: zanim Kontroler zacznie strumieniować odpowiedź węzła, wysyła jeden własny event z metadanymi routingu.

**Co zmienić:** W funkcji `_proxy_sse_to_queue`, wewnątrz pętli `for worker in workers:`, zaraz po linii `worker_url = f"{worker['base_url']}/v1/chat/stream"` i **przed** wywołaniem `requests.post(...)`, dodać emisję eventu `routing_info`:

```python
# DODAJ te 5 linii przed resp = requests.post(...)
routing_event = {
    "type": "routing_info",
    "worker_id": worker["id"],
    "model": worker.get("model_name", "nieznany"),
    "tier": worker.get("tier", "nieznany"),
}
loop.call_soon_threadsafe(q.put_nowait, routing_event)
```

Event jest wysyłany przez Kontrolera z własnej wiedzy (ma te dane w rejestrze) — nie wymaga żadnych zmian w węźle.

> [!NOTE]
> Upewnij się że ta emisja następuje **po** sprawdzeniu `worker_url` ale **przed** `requests.post`. Chodzi o to żeby event był wysłany zanim pojawią się tokeny odpowiedzi — klient musi wiedzieć kto odpowiada zanim zobaczy treść.

---

## 1.2 Zmiana w `node/worker.py`

**Dlaczego:** Event `"done"` który węzeł wysyła na koniec nie zawiera czasu trwania inferencji. Monitor chce wyświetlić "3.1s" w linii statusu. Rozwiązanie: mierzymy czas przed i po `handle_chat()` i dołączamy do eventu `done`.

**Co zmienić:** W funkcji `run_inference()` wewnątrz endpointu `chat_stream` (linia ~166):

```python
# PRZED zmianą:
def run_inference():
    try:
        response_text = worker_node.handle_chat(
            request.message, remote_tools, ...
        )
        loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": response_text})

# PO zmianie (dodaj import time na górze pliku jeśli go nie ma):
def run_inference():
    try:
        import time
        _start = time.time()
        response_text = worker_node.handle_chat(
            request.message, remote_tools, ...
        )
        elapsed_ms = int((time.time() - _start) * 1000)
        loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": response_text, "elapsed_ms": elapsed_ms})
```

To samo zrób w `run_inference()` wewnątrz `chat_audio_stream` — ta funkcja też wysyła event `"done"`.

> [!NOTE]
> `import time` prawdopodobnie nie jest jeszcze na górze `worker.py`. Dodaj go do bloku importów na początku pliku, nie lokalnie w funkcji.

---

## 1.3 Przepisanie `regis_cli/chat.py`

**Dlaczego:** Aktualny `chat.py` używa `RemoteClient.generate_response()` jako abstrakcji nad SSE. Problem: `RemoteClient` nie obsługuje nowego eventu `routing_info` — ignoruje wszystkie nieznane typy eventów (patrz `core/remote_client.py` linia ~46, gdzie jest tylko `thought`, `content`, `tool`, `done`, `error`). Zamiast dodawać `on_routing_info` do RemoteClient (który jest ogólnym klientem), Monitor czyta SSE **bezpośrednio** przez `requests` — tak samo jak robi to `router.py` w Kontrolerze. Dzięki temu Monitor ma pełną kontrolę nad obsługą wszystkich typów eventów.

**Dodatkowe problemy do naprawienia w tym pliku:**
- Nagłówek używa złej nazwy `"Transparentny Panel (Podgląd LLM)"` — zastąpić `"Monitor"`
- Kolor `"bold magenta"` na `"Regis:"` — narusza zasady estetyczne projektu. Zastąpić `"bold white"`.
- Emoji `🛠` w obsłudze narzędzi — usunąć. Zastąpić tekstem `[narzedzie]`.
- Brak timestampów
- Brak obsługi slash komend

**Pełna nowa wersja pliku** (zastąp całą zawartość `chat.py`):

```python
import json
import sys
import time
import requests
from datetime import datetime

import questionary
from rich.console import Console
from rich.rule import Rule

from core import config
from core.exceptions import LLMConnectionError
from regis_cli.ux import console, custom_style


# ─── Stan wewnętrzny monitora ─────────────────────────────────────────────────
_verbose = False


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _format_elapsed(elapsed_ms: int | None) -> str:
    if elapsed_ms is None:
        return ""
    if elapsed_ms < 1000:
        return f"{elapsed_ms}ms"
    return f"{elapsed_ms / 1000:.1f}s"


def _handle_slash_command(cmd: str, server_url: str) -> bool:
    """Obsługuje wewnętrzne komendy monitora. Zwraca True jeśli komenda została rozpoznana."""
    global _verbose
    cmd = cmd.strip().lower()

    if cmd == "/verbose":
        _verbose = not _verbose
        state = "włączony" if _verbose else "wyłączony"
        console.print(f"[dim]Tryb szczegółowy {state}.[/dim]\n")
        return True

    if cmd == "/clear":
        console.clear()
        try:
            requests.post(f"{server_url}/v1/clear_history", timeout=5)
            console.print("[dim]Historia konwersacji wyczyszczona.[/dim]\n")
        except Exception:
            console.print("[dim]Nie udało się wyczyścić historii na serwerze.[/dim]\n")
        return True

    if cmd == "/help":
        console.print("[dim]Dostępne komendy:[/dim]")
        console.print("[dim]  /verbose  — przełącza tryb szczegółowy (myśli i narzędzia)[/dim]")
        console.print("[dim]  /clear    — czyści ekran i historię konwersacji[/dim]")
        console.print("[dim]  /help     — wyświetla tę pomoc[/dim]")
        console.print("[dim]  /exit     — wychodzi z monitora[/dim]\n")
        return True

    if cmd == "/exit":
        return False  # sygnał do wyjścia — obsłużony wyżej w pętli

    console.print(f"[dim]Nieznana komenda: {cmd}. Wpisz /help aby zobaczyć dostępne komendy.[/dim]\n")
    return True


def _stream_and_display(prompt: str, server_url: str) -> None:
    """Wysyła wiadomość do Kontrolera i wyświetla strumień zdarzeń SSE."""
    global _verbose

    timestamp = _timestamp()
    console.print(f"[dim][{timestamp}][/dim] [bold white]Ty:[/bold white] {prompt}")

    # Bufor stanu dla trybu normalnego
    routing: dict | None = None
    tool_calls: list[str] = []
    final_text = ""
    elapsed_ms: int | None = None

    try:
        url = f"{server_url}/v1/chat/stream"
        payload = {"message": prompt}
        resp = requests.post(url, json=payload, stream=True, timeout=300)
        resp.raise_for_status()

        # Flaga do obsługi streamingu myśli w verbose (otwieramy blok raz)
        thought_open = False

        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue

            ev_type = event.get("type")
            content = event.get("content", "")

            if ev_type == "routing_info":
                routing = event
                if _verbose:
                    worker_id = event.get("worker_id", "?")
                    model = event.get("model", "?")
                    tier = event.get("tier", "?")
                    console.print(f"  [dim]→ {worker_id}  {model}  tier: {tier}[/dim]")

            elif ev_type == "thought":
                if _verbose:
                    if not thought_open:
                        console.print("\n  [dim]<myśl>[/dim]")
                        thought_open = True
                    console.print(f"  [dim]{content}[/dim]", end="")
                    sys.stdout.flush()
                # W trybie normalnym — cisza. Myśli są szczegółem implementacyjnym.

            elif ev_type == "content":
                if thought_open:
                    # Zamknij blok myśli przed treścią odpowiedzi
                    console.print("\n  [dim]</myśl>[/dim]\n")
                    thought_open = False
                console.print(f"{content}", end="", style="bold white")
                sys.stdout.flush()

            elif ev_type == "tool":
                if thought_open:
                    console.print("\n  [dim]</myśl>[/dim]", end="")
                    thought_open = False
                tool_calls.append(content)
                if _verbose:
                    console.print(f"\n  [dim][narzedzie] {content}[/dim]")

            elif ev_type == "done":
                final_text = content
                elapsed_ms = event.get("elapsed_ms")
                if thought_open:
                    console.print("\n  [dim]</myśl>[/dim]")
                    thought_open = False

            elif ev_type == "error":
                console.print(f"\n[red]Błąd serwera:[/red] {content}")
                return

    except requests.RequestException as e:
        console.print(f"\n[red]Błąd połączenia:[/red] {e}")
        return

    # ─── Linia statusu po odpowiedzi ─────────────────────────────────────────
    # Zawsze wyświetlana. W trybie verbose jest krótsza (routing był już wyżej).
    status_parts = []
    if not _verbose and routing:
        worker_id = routing.get("worker_id", "")
        model = routing.get("model", "")
        if worker_id:
            status_parts.append(worker_id)
        if model:
            status_parts.append(model)
    if tool_calls:
        n = len(tool_calls)
        status_parts.append(f"{n} {'narzędzie' if n == 1 else 'narzędzia' if n < 5 else 'narzędzi'}")
    if elapsed_ms is not None:
        status_parts.append(_format_elapsed(elapsed_ms))

    if status_parts:
        console.print(f"\n  [dim]·  {'  '.join(status_parts)}[/dim]")
    else:
        console.print()  # pusty wiersz dla oddechu


def run_monitor() -> None:
    """Uruchamia monitor konwersacji — interaktywny podgląd przepływu Kontroler ↔ Węzeł."""
    global _verbose

    console.print()
    console.rule("[bold white]Monitor[/bold white]", style="dim")
    console.print()

    settings = config.load_settings()
    server_url = settings.get("server_url", settings.get("controller_url", "http://127.0.0.1:8000"))

    if server_url == "auto":
        from core.discovery import discover_controller
        try:
            server_url = discover_controller()
        except Exception as e:
            console.print(f"[red]Auto-Discovery zawiodło:[/red] {e}")
            ip = questionary.text(
                "Podaj adres IP Kontrolera:",
                default="192.168.0.119",
                style=custom_style
            ).ask()
            server_url = f"http://{ip or '127.0.0.1'}:8000"

    console.print(f"[dim]Kontroler: {server_url}[/dim]")
    console.print("[dim]Komendy: /verbose /clear /help /exit[/dim]")
    console.print()

    while True:
        try:
            prompt = questionary.text("Ty:", style=custom_style).ask()

            if prompt is None:
                break

            prompt = prompt.strip()

            if not prompt:
                continue

            if prompt.startswith("/"):
                if prompt.lower() == "/exit":
                    break
                _handle_slash_command(prompt, server_url)
                continue

            console.print()
            _stream_and_display(prompt, server_url)
            console.print()

        except KeyboardInterrupt:
            break

    console.print("[dim]Zamknięto monitor.[/dim]\n")


# Alias wstecznej kompatybilności — dashboard.py i regis_cli/main.py importują dev_chat
dev_chat = run_monitor
```

> [!IMPORTANT]
> Zwróć uwagę na alias `dev_chat = run_monitor` na końcu pliku. Dzięki temu nie musisz od razu zmieniać importów w `dashboard.py` i `main.py` — to możesz zrobić w tym samym commicie ale nie jest krytyczne.

---

## 1.4 Nazewnictwo — dwa małe pliki

### `node/dashboard.py` — linia 75

```python
# PRZED:
"Transparentny Panel (Podgląd LLM)",

# PO:
"Monitor",
```

Oraz linia 95 (w bloku obsługi wyboru):
```python
# PRZED:
elif choice == "Transparentny Panel (Podgląd LLM)":

# PO:
elif choice == "Monitor":
```

### `regis_cli/main.py` — linia 19

```python
# PRZED:
"[Narzędzia] Chat z serwerem (Dev)",

# PO:
"[Narzędzia] Monitor",
```

Oraz linia 39 (w bloku obsługi wyboru):
```python
# PRZED:
elif "[Narzędzia]" in choice and "Chat" in choice:

# PO:
elif "[Narzędzia]" in choice and "Monitor" in choice:
```

---

## 1.5 Weryfikacja Etapu 1

Po wdrożeniu uruchom i sprawdź ręcznie:

1. `python -m regis_cli` → opcja powinna się nazywać `"[Narzędzia] Monitor"`.
2. Wejdź w Monitor → nagłówek powinien wyświetlić `Monitor` (przez `console.rule`).
3. Napisz coś do systemu → sprawdź czy pojawia się linia statusu `· węzeł  model  czas` po odpowiedzi.
4. Wpisz `/verbose` → system potwierdza włączenie, kolejna odpowiedź pokazuje blok `→ węzeł` i `<myśl>`.
5. Wpisz `/help` → lista komend bez błędów.
6. Wpisz `/exit` → wyjście z monitora.
7. `python -m node.main --dashboard` → opcja `"Monitor"` w menu.
8. Sprawdź że nie ma **emoji**, nie ma **magenta**, nie ma **cyan** jako kolorów dekoracyjnych.

---

---

# ETAP 2: Refaktoryzacja Traya — Usługa i Panel Kontrolny

> [!IMPORTANT]
> Nie implementuj Etapu 2 bez oddzielnego polecenia od użytkownika. Etap 1 jest kompletny sam w sobie.

## Cel i architektura

**Obecnie:**
- `tray.py` = usługa + UI sterowania (menu z 6 pozycjami)
- `dashboard.py` = panel który uruchamia/zatrzymuje tray (jeden kanał: plik `shutdown.flag`)

**Docelowo:**
- `tray.py` = czysta usługa. Właściciel procesów Worker i Satellite. Menu ma 3 pozycje.
- `tray.py` wystawia **lokalny HTTP API** na `localhost:8099` dla dashboardu.
- `dashboard.py` = pełny panel sterowania. Pyta tray przez HTTP o status. Wysyła komendy start/stop.

**Tray menu po zmianie:**
```
Regis Node — [nazwa]       ← nieaktywna etykieta
──────────────────────
Otwórz panel kontrolny     ← otwiera dashboard w nowej konsoli
──────────────────────
Zamknij                    ← zatrzymuje worker + satellite + tray
```

Opcje `"Worker LLM"`, `"Satellite"`, `"Autostart"`, `"Konfiguracja"` znikają z menu traya — przenoszą się do dashboardu.

> [!WARNING]
> **Zamknij = zatrzymuje absolutnie wszystko.** Usuwamy opcję `"Zamknij panel (procesy działają)"` — zamknięcie traya zawsze zatrzymuje Worker i Satellite. To jest decyzja projektowa, nie błąd.

---

## 2.1 Mini HTTP API w `tray.py`

**Dlaczego HTTP a nie pliki flag:** Pliki flag działają dla jednej komendy (shutdown). Dla dynamicznego statusu i wielu komend potrzebny jest mechanizm zapytanie-odpowiedź. HTTP jest wyborem naturalnym — cały projekt komunikuje się przez HTTP (Kontroler, Worker). Używamy biblioteki stdlib `http.server` — zero nowych zależności.

**Port:** `8099` — wybrany tak żeby nie kolidować z Kontrolerem (8000) ani Workerem (8001).

**Dodaj do `tray.py`** nową funkcję serwera i uruchom ją w wątku:

```python
import socketserver
from http.server import BaseHTTPRequestHandler
import urllib.parse

MANAGEMENT_PORT = 8099

class _TrayHandler(BaseHTTPRequestHandler):
    """Minimalistyczny HTTP handler dla API zarządzania trayem."""

    def log_message(self, format, *args):
        pass  # wycisz logi HTTP w konsoli

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._send_json({
                "worker": "running" if is_worker_running() else "stopped",
                "satellite": "running" if is_satellite_running() else "stopped",
                "autostart_worker": get_settings().get("autostart_worker", False),
                "autostart_satellite": get_settings().get("autostart_satellite", False),
            })
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/worker/toggle":
            if is_worker_running():
                stop_worker()
            else:
                start_worker()
            self._send_json({"worker": "running" if is_worker_running() else "stopped"})

        elif self.path == "/satellite/toggle":
            if is_satellite_running():
                stop_satellite()
            else:
                start_satellite()
            self._send_json({"satellite": "running" if is_satellite_running() else "stopped"})

        elif self.path == "/shutdown":
            self._send_json({"status": "shutting_down"})
            # Dajemy chwilę na odesłanie odpowiedzi, potem zamykamy
            threading.Thread(target=lambda: (time.sleep(0.5), quit_all(None, None))).start()

        else:
            self._send_json({"error": "not found"}, 404)


def _start_management_server():
    """Uruchamia serwer zarządzania w tle (daemon thread)."""
    try:
        server = socketserver.TCPServer(("127.0.0.1", MANAGEMENT_PORT), _TrayHandler)
        server.serve_forever()
    except OSError as e:
        # Port zajęty — inna instancja traya prawdopodobnie działa
        print(f"Management server nie mógł wystartować na porcie {MANAGEMENT_PORT}: {e}")
```

W funkcji `run_tray()`, przed `icon.run()`, dodaj uruchomienie serwera w wątku:

```python
mgmt_thread = threading.Thread(target=_start_management_server, daemon=True)
mgmt_thread.start()
```

Oraz zaktualizuj `quit_all()` aby upewnić się że serwer nie blokuje zamknięcia — daemon thread zamknie się automatycznie razem z procesem.

---

## 2.2 Uproszczenie menu w `tray.py`

Zastąp całą funkcję `get_menu()`:

```python
def get_menu():
    settings = get_settings()
    name = settings.get("instance_name", "Regis Node")
    return pystray.Menu(
        item(lambda text: f"Regis Node — {name}", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("Otwórz panel kontrolny", open_dashboard),
        pystray.Menu.SEPARATOR,
        item("Zamknij", quit_all),
    )
```

Dodaj nową funkcję `open_dashboard()`:

```python
def open_dashboard():
    cmd = get_executable_command("--dashboard")
    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
```

> [!NOTE]
> `CREATE_NEW_CONSOLE` jest kluczowe — to jest właśnie naprawa buga "Konfiguracja nie otwiera konsoli". Poprzedni `run_wizard_from_tray` używał `subprocess.Popen(cmd)` bez tej flagi, przez co potomek dziedziczył (brak) konsoli od procesu tray.

Usuń z pliku funkcje które nie są już potrzebne:
- `toggle_worker()`, `toggle_satellite()` — obsługiwane przez HTTP API
- `toggle_autostart()`, `is_autostart_enabled()` — przenosi się do dashboardu
- `quit_panel()` — opcja nie istnieje w nowym menu

---

## 2.3 Przepisanie `node/dashboard.py`

Dashboard staje się **klientem HTTP API traya**. Wie o stanie usługi przez `GET /status`. Wydaje komendy przez `POST /worker/toggle` itp.

Dodaj helper do komunikacji z API traya:

```python
import requests

TRAY_API = "http://127.0.0.1:8099"

def _tray_get_status() -> dict | None:
    """Pobiera status z API traya. Zwraca None jeśli tray nie działa."""
    try:
        resp = requests.get(f"{TRAY_API}/status", timeout=1.0)
        return resp.json()
    except Exception:
        return None

def _tray_post(path: str) -> bool:
    """Wysyła komendę do traya. Zwraca True jeśli sukces."""
    try:
        requests.post(f"{TRAY_API}{path}", timeout=2.0)
        return True
    except Exception:
        return False
```

Zaktualizuj `is_tray_running()` — zamiast skanowania procesów, próbuj połączyć się z API:

```python
def is_tray_running() -> bool:
    return _tray_get_status() is not None
```

Zaktualizuj `print_header()` aby wyświetlał status Worker i Satellite z API:

```python
def print_header():
    console.clear()
    console.print("\n[bold white]Regis Node — Panel Kontrolny[/bold white]")
    console.rule(style="dim")

    status = _tray_get_status()
    if status is None:
        console.print("[dim]Usługa nie działa.[/dim]\n")
        return

    worker_str = "[green]działa[/green]" if status["worker"] == "running" else "[dim]zatrzymany[/dim]"
    satellite_str = "[green]działa[/green]" if status["satellite"] == "running" else "[dim]zatrzymany[/dim]"
    console.print(f"Worker LLM:  {worker_str}")
    console.print(f"Satellite:   {satellite_str}\n")
```

Zaktualizuj `run_dashboard()` — nowe menu z opcjami sterowania:

```python
def run_dashboard():
    while True:
        print_header()
        status = _tray_get_status()
        tray_running = status is not None

        choices = []
        if tray_running:
            worker_action = "Zatrzymaj Worker LLM" if status["worker"] == "running" else "Uruchom Worker LLM"
            satellite_action = "Zatrzymaj Satellite" if status["satellite"] == "running" else "Uruchom Satellite"
            choices += [worker_action, satellite_action, questionary.Separator()]
            choices += ["Konfiguracja...", "Monitor", questionary.Separator()]
            choices += ["Zatrzymaj usługę"]
        else:
            choices += ["Uruchom usługę w tle", questionary.Separator()]
            choices += ["Konfiguracja...", "Monitor", questionary.Separator()]

        choices.append("Wyjście")

        choice = questionary.select("Wybierz akcję:", choices=choices, style=custom_style).ask()

        if not choice or choice == "Wyjście":
            break
        elif choice in ("Uruchom Worker LLM", "Zatrzymaj Worker LLM"):
            _tray_post("/worker/toggle")
        elif choice in ("Uruchom Satellite", "Zatrzymaj Satellite"):
            _tray_post("/satellite/toggle")
        elif choice == "Uruchom usługę w tle":
            start_tray()
        elif choice == "Zatrzymaj usługę":
            _tray_post("/shutdown")
            time.sleep(1.5)
        elif choice == "Konfiguracja...":
            run_wizard()
        elif choice == "Monitor":
            from regis_cli.chat import run_monitor
            run_monitor()
```

---

## 2.4 Weryfikacja Etapu 2

1. Uruchom `python -m node.main --tray` → ikona pojawia się w trayu.
2. Menu traya ma **3 pozycje**: etykieta z nazwą, "Otwórz panel kontrolny", "Zamknij".
3. Kliknij "Otwórz panel kontrolny" → otwiera się nowe okno konsoli z dashboardem.
4. W dashboardzie widoczny status Worker i Satellite.
5. Opcja "Uruchom Worker LLM" / "Zatrzymaj Worker LLM" działa — status się odświeża.
6. "Zamknij" w trayu zamyka ikonę **i** zatrzymuje Worker i Satellite.
7. Sprawdź że port 8099 jest zajęty gdy tray działa: `netstat -an | findstr 8099`.

---

## Pliki zmieniane — zestawienie

| Etap | Plik | Typ zmiany |
|---|---|---|
| 1 | `controller/router.py` | Dodanie emisji eventu `routing_info` |
| 1 | `node/worker.py` | Dodanie `elapsed_ms` do eventu `done` |
| 1 | `regis_cli/chat.py` | Pełne przepisanie — nowy Monitor |
| 1 | `node/dashboard.py` | Zmiana nazwy opcji menu |
| 1 | `regis_cli/main.py` | Zmiana nazwy opcji menu |
| 2 | `node/tray.py` | Mini HTTP API + uproszczenie menu |
| 2 | `node/dashboard.py` | Przepisanie na klienta HTTP API |
| 3 | `node/dashboard.py` | Unifikacja wizualna — styl i typografia |

---

---

# ETAP 3: Unifikacja Wizualna Dashboardu

> [!IMPORTANT]
> Nie implementuj Etapu 3 bez oddzielnego polecenia od użytkownika. Wymaga ukończonego Etapu 2.

## Cel

Po Etapie 2 dashboard działa poprawnie, ale wizualnie jest niespójny z resztą CLI — używa surowego `questionary` bez `custom_style`, innego formatowania nagłówków itp. Ten etap ujednolica wygląd dashboardu z `regis_cli/main.py` i nowym Monitorem.

**Plik:** tylko `node/dashboard.py`

## Co zmienić

### Import stylu z `regis_cli.ux`

Dodaj na górze pliku:

```python
from regis_cli.ux import console, custom_style
```

Usuń lokalne `console = Console()` jeśli takie istnieje w pliku po Etapie 2.

### Wszystkie wywołania `questionary.select()`

Każde wywołanie `questionary.select(...)` musi mieć `style=custom_style`:

```python
# PRZED:
choice = questionary.select("Wybierz akcję:", choices=choices).ask()

# PO:
choice = questionary.select("Wybierz akcję:", choices=choices, style=custom_style).ask()
```

### Nagłówek — spójny z resztą CLI

Zaktualizuj `print_header()` żeby używał `console.rule()` zamiast linii `=`:

```python
def print_header():
    console.clear()
    console.print()
    console.rule("[bold white]Regis Node — Panel Kontrolny[/bold white]", style="dim")
    console.print()
    # ... reszta bez zmian
```

### Weryfikacja Etapu 3

1. Uruchom dashboard — nagłówek powinien wyglądać jak w Monitorze (pozioma linia `Rule`).
2. Menu questionary powinno używać wyciszonego motywu (szare podświetlenie, nie niebieski/żółty domyślny).
3. Brak lokalno-zdefiniowanego `console = Console()` — używany jest ten z `regis_cli.ux`.
