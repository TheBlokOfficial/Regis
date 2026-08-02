import json
import sys
import time
import os
import threading

if os.name == 'nt':
    import msvcrt

import requests
from rich.rule import Rule

from node.legacy.ux import console
from node.legacy.monitor_core import render_user_turn, TurnRenderer

SERVICE_URL = "http://127.0.0.1:8099"
SSE_RECONNECT_DELAY = 3

_STATE_LABELS = {
    "WAKEWORD": "[bold green]⭘ Gotowość – nasłuchuję wake word ('Regis')[/]",
    "LISTENING": "[bold red]● Wykryto mowę – nagrywanie w toku...[/]",
    "RESPONDING": "[bold cyan]🗣 Rozmowa w toku...[/]",
}

_verbose = True

def _redraw_header(state: str, clear: bool = True) -> None:
    # Wymusza poprawne, stuprocentowe wyczyszczenie bufora konsoli z użyciem systemowego cls na Windows.
    # Używamy os.system, bo console.clear() zawiodło na obecnym środowisku terminala użytkownika.
    if clear:
        os.system('cls' if os.name == 'nt' else 'clear')
    else:
        console.print()
    console.print(Rule("Monitor Głosowy", style="info"))
    label = _STATE_LABELS.get(state, f"[{state}]")
    console.print(label, justify="center")
    console.print(Rule(style="dim"))


def _update_header_inplace(state: str) -> None:
    """Używa kodów ANSI do podmiany samej środkowej linijki nagłówka bez czyszczenia okna."""
    label = _STATE_LABELS.get(state, f"[{state}]")
    # Zapisz pozycję (SCO i DEC)
    sys.stdout.write("\0337\033[s")
    # Skocz do 2. linii (zakładając że Rule() zajął 1. linię po cls), wyczyść linię
    sys.stdout.write("\033[2;1H\033[2K")
    sys.stdout.flush()
    # Wydrukuj nową treść
    console.print(label, justify="center")
    # Odtwórz pozycję (SCO i DEC)
    sys.stdout.write("\0338\033[u")
    sys.stdout.flush()


def _subscribe_sse():
    while True:
        try:
            # Sprawdź najpierw status satelity
            try:
                status_resp = requests.get(f"{SERVICE_URL}/status", timeout=2)
                if status_resp.status_code == 200:
                    status_data = status_resp.json()
                    if status_data.get("satellite") != "running":
                        console.print("[warning]Satelita nie jest aktualnie uruchomiony. Monitor czeka na jego start...[/warning]")
            except Exception:
                pass

            with requests.get(
                f"{SERVICE_URL}/satellite/events",
                stream=True,
                timeout=(5, None),
            ) as resp:
                for raw_line in resp.iter_lines(chunk_size=1):
                    if raw_line and raw_line.startswith(b"data: "):
                        try:
                            yield json.loads(raw_line[6:])
                        except json.JSONDecodeError:
                            pass
        except KeyboardInterrupt:
            return
        except Exception as e:
            console.print(
                f"[info]Brak połączenia z service.py ({e}). "
                f"Ponawiam za {SSE_RECONNECT_DELAY}s...[/info]"
            )
            try:
                time.sleep(SSE_RECONNECT_DELAY)
            except KeyboardInterrupt:
                return


def _keyboard_listener():
    global _verbose
    from node import config
    settings = config.load_settings()
    server_url = settings.get("server_url", settings.get("controller_url", "http://127.0.0.1:8000"))
    if server_url == "auto":
        from protocol.discovery import discover_controller
        try:
            server_url = discover_controller()
        except Exception:
            server_url = "http://127.0.0.1:8000"

    while True:
        if os.name == 'nt' and msvcrt.kbhit():
            key = msvcrt.getwch().lower()
            if key == 'v':
                _verbose = not _verbose
                state = "włączony" if _verbose else "wyłączony"
                console.print(f"\n[info]Tryb szczegółowy (Verbose) {state}.[/info]")
            elif key == 'c':
                try:
                    requests.post(f"{server_url}/v1/clear_history", timeout=5)
                    _redraw_header("WAKEWORD")
                    console.print("\n[info]Historia konwersacji (pamięć serwera) została wyczyszczona.[/info]")
                except Exception:
                    console.print("\n[error]Nie udało się połączyć z Kontrolerem w celu wyczyszczenia pamięci.[/error]")
            elif key == '\x03': # Ctrl+C
                console.print("\n[info]Zamknięto monitor głosowy (Wymuszenie Ctrl+C).[/info]")
                os._exit(0)
        time.sleep(0.05)


def run_voice_monitor() -> None:
    global _verbose
    
    t = threading.Thread(target=_keyboard_listener, daemon=True)
    t.start()
    
    _redraw_header("WAKEWORD")

    renderer = None
    routing_info_cache = None

    try:
        for event in _subscribe_sse():
            typ = event.get("type")

            if typ == "routing_info":
                routing_info_cache = event
                if renderer:
                    renderer.on_routing_info(event)

            elif typ == "state":
                state = event.get("state", "")
                if state == "WAKEWORD":
                    _update_header_inplace("WAKEWORD")
                elif state == "LISTENING":
                    # Czyszczenie i nowa tablica DOPIERO na słowo "Regis" 
                    _redraw_header("LISTENING")
                elif state == "RESPONDING":
                    _redraw_header("RESPONDING")

            elif typ == "stt_partial":
                text = event.get("text", "")
                sys.stdout.write(f"\r\033[K[dim]... {text}[/dim]")
                sys.stdout.flush()

            elif typ == "stt_result":
                text = event.get("text", "")
                _redraw_header("RESPONDING") # Czyści jednokrotnie i płynnie podgląd na żywo, odmalowując piękne żółte pole RESPONDING na sam start odp.
                render_user_turn(text)
                renderer = TurnRenderer(verbose=_verbose)
                if routing_info_cache:
                    renderer.on_routing_info(routing_info_cache)

            elif typ == "thought":
                if renderer:
                    renderer.on_thought_token(event.get("content", ""))

            elif typ == "content":
                if renderer:
                    renderer.on_content_token(event.get("content", ""))

            elif typ == "tool":
                if renderer:
                    renderer.on_tool_call(event.get("name", event.get("token", "")))

            elif typ == "profiler":
                if renderer:
                    renderer.on_profiler(event.get("content", {}))

            elif typ == "done":
                if renderer:
                    renderer.on_done(event)
                    renderer.render_status_line()
                    renderer = None
                console.print()

            elif typ == "info":
                # Celowo ignorujemy techniczne logi satelity (Złapano rutowanie, EOF, Websocket), 
                # aby nie brudziły one czystego Dashboardu z rozmową (ale zachowujemy _verbose=True dla TurnRenderer'a).
                pass

            elif typ == "error":
                if renderer:
                    renderer.close_thought()
                    renderer = None
                console.print(f"\n[error]Błąd satelity:[/error] {event.get('message', '')}")

    except KeyboardInterrupt:
        pass

    console.print("\n[info]Zamknięto monitor głosowy.[/info]\n")


if __name__ == "__main__":
    run_voice_monitor()
