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
from node.ux import console, custom_style
from prompt_toolkit.history import InMemoryHistory

# ─── Stan wewnętrzny monitora ─────────────────────────────────────────────────
_verbose = False
_history = InMemoryHistory()


def _handle_slash_command(cmd: str, server_url: str) -> bool:
    """Obsługuje wewnętrzne komendy monitora. Zwraca True jeśli komenda została rozpoznana."""
    global _verbose
    cmd = cmd.strip().lower()

    if cmd == "/verbose":
        _verbose = not _verbose
        state = "włączony" if _verbose else "wyłączony"
        console.print(f"[info]Tryb szczegółowy {state}.[/info]\n")
        return True

    if cmd == "/clear":
        import os
        os.system("cls" if os.name == "nt" else "clear")
        try:
            requests.post(f"{server_url}/v1/clear_history", timeout=5)
            console.print("[info]Historia konwersacji wyczyszczona.[/info]\n")
        except Exception:
            console.print("[info]Nie udało się wyczyścić historii na serwerze.[/info]\n")
        return True

    if cmd == "/help":
        console.print("[info]Dostępne komendy:[/info]")
        console.print("[info]  /verbose  — przełącza tryb szczegółowy (myśli i narzędzia)[/info]")
        console.print("[info]  /clear    — czyści ekran i historię konwersacji[/info]")
        console.print("[info]  /help     — wyświetla tę pomoc[/info]")
        console.print("[info]  /exit     — wychodzi z monitora[/info]\n")
        return True

    if cmd == "/exit":
        return False  # sygnał do wyjścia — obsłużony wyżej w pętli

    console.print(f"[info]Nieznana komenda: {cmd}. Wpisz /help aby zobaczyć dostępne komendy.[/info]\n")
    return True


def _stream_and_display(prompt: str, server_url: str) -> None:
    """Odbiera zdarzenia SSE poprzez Satelitę (RemoteClient) i renderuje turę."""
    global _verbose

    from node.remote_client import RemoteClient
    from core.config import load_settings
    from node.monitor_core import render_user_turn, TurnRenderer

    settings = load_settings()
    satellite_id = settings.get("instance_name")

    client = RemoteClient(base_url=server_url, satellite_id=satellite_id)
    renderer = TurnRenderer(verbose=_verbose)

    render_user_turn(prompt)

    try:
        final_text = client.generate_response(
            prompt=prompt,
            tools_registry=None,
            on_tool_call=renderer.on_tool_call,
            on_thought_token=renderer.on_thought_token,
            on_content_token=renderer.on_content_token,
            on_routing_info=renderer.on_routing_info,
            on_done=renderer.on_done,
            on_profiler=renderer.on_profiler
        )
    except Exception as e:
        console.print(f"\n[error]Błąd komunikacji z serwerem:[/error] {e}")
        return

    renderer.finalize_response(final_text)
    renderer.render_status_line()


def run_monitor() -> None:
    """Uruchamia monitor konwersacji — interaktywny podgląd przepływu Kontroler ↔ Węzeł."""
    global _verbose

    console.print()
    console.rule("[header]Monitor[/header]", style="info")
    console.print()

    settings = config.load_settings()
    server_url = settings.get("server_url", settings.get("controller_url", "http://127.0.0.1:8000"))

    if server_url == "auto":
        from core.discovery import discover_controller
        try:
            server_url = discover_controller()
        except Exception as e:
            console.print(f"[error]Auto-Discovery zawiodło:[/error] {e}")
            ip = questionary.text(
                "Podaj adres IP Kontrolera:",
                default="192.168.0.119",
                style=custom_style
            ).ask()
            server_url = f"http://{ip or '127.0.0.1'}:8000"

    console.print(f"[info]Kontroler:[/info] [header]{server_url}[/header]")
    console.print("[info]Komendy:[/info] [header]/verbose[/header] [header]/clear[/header] [header]/help[/header] [header]/exit[/header]")
    console.print()

    while True:
        try:
            prompt = questionary.text("Ty:", style=custom_style, history=_history).ask()

            if prompt is None:
                break
                
            # Obliczamy ile fizycznych linii terminala zajmuje tekst użytkownika
            import shutil
            term_width = shutil.get_terminal_size().columns
            prompt_len = len("? Ty: ") + len(prompt)
            lines_to_clear = (prompt_len // term_width) + 1 + prompt.count('\n')
            
            # Kasujemy z ekranu całą "resztkę" po questionary
            for _ in range(lines_to_clear):
                sys.stdout.write("\033[F\033[K")
            sys.stdout.flush()

            prompt = prompt.strip()

            if not prompt:
                continue

            if prompt.startswith("/"):
                if prompt.lower() == "/exit":
                    break
                _handle_slash_command(prompt, server_url)
                continue

            _stream_and_display(prompt, server_url)
            console.print()

        except KeyboardInterrupt:
            break

    console.print("[info]Zamknięto monitor.[/info]\n")


# Alias wstecznej kompatybilności — dashboard.py i main.py importują dev_chat
dev_chat = run_monitor
