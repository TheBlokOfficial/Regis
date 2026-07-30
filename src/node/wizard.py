import os
import json
import socket
import requests
import questionary

from node.ux import console
from rich.rule import Rule
from core.discovery import discover_controller
from core.config import load_settings

def run_wizard():
    console.print()
    console.print(Rule("[bold white]Regis Node: Konfiguracja Początkowa[/bold white]", style="info"))
    console.print()
    
    current_cfg = load_settings()
    
    instance_name = questionary.text(
        "Nazwa tej instancji:", 
        default=current_cfg.get("instance_name", f"Node-{socket.gethostname()}")
    ).ask()
    
    controller_url_input = questionary.text(
        "URL Kontrolera (wpisz 'auto' dla wykrywania po UDP):", 
        default=current_cfg.get("controller_url", "auto")
    ).ask()
    
    resolved_controller_url = controller_url_input
    if resolved_controller_url == "auto":
        console.print("[dim]Szukanie kontrolera w sieci lokalnej (UDP)...[/dim]")
        try:
            resolved_controller_url = discover_controller()
            console.print(f"[bold green]Znaleziono Kontroler:[/bold green] {resolved_controller_url}")
        except Exception as e:
            console.print(f"[bold red]Nie udało się automatycznie znaleźć kontrolera:[/bold red] {e}")
            resolved_controller_url = questionary.text(
                "Podaj ręcznie adres URL Kontrolera (np. http://192.168.0.119:8000):"
            ).ask()
            
    available_rooms = []
    try:
        resp = requests.get(f"{resolved_controller_url}/v1/rooms", timeout=3)
        if resp.ok:
            available_rooms = resp.json().get("rooms", [])
    except Exception as e:
        console.print(f"[bold yellow]Ostrzeżenie: Nie udało się pobrać listy pokoi z Kontrolera ({e}).[/bold yellow]")
        
    room_choices = available_rooms + ["[Wpisz ręcznie inny pokój]"]
    
    default_room_idx = 0
    saved_room = current_cfg.get("room")
    if saved_room in available_rooms:
        default_room_idx = available_rooms.index(saved_room)
    elif saved_room:
        default_room_idx = len(room_choices) - 1  # Wpisz ręcznie
        
    selected_room = questionary.select(
        "W którym pokoju znajduje się ten węzeł?",
        choices=room_choices,
        default=room_choices[default_room_idx]
    ).ask()
    
    if selected_room == "[Wpisz ręcznie inny pokój]" or not selected_room:
        room = questionary.text(
            "Wpisz własną nazwę pokoju (np. salon):",
            default=current_cfg.get("room", "salon")
        ).ask()
    else:
        room = selected_room
    
    tier_choices = ["butler (1.5B)", "regis (9B)"]
    saved_tier = current_cfg.get("active_tier", "regis")
    default_tier_str = "regis (9B)"
    for t in tier_choices:
        if t.startswith(saved_tier):
            default_tier_str = t
            break
            
    active_tier = questionary.select(
        "Wybierz Tier modelu LLM (poziom inteligencji):",
        choices=tier_choices,
        default=default_tier_str
    ).ask()
    
    active_tier = active_tier.split(" ")[0]
    
    print("\nUsługi w tle:")
    run_worker = questionary.confirm("Uruchamiać Worker (LLM) automatycznie?", default=current_cfg.get("autostart_worker", True)).ask()
    run_satellite = questionary.confirm("Uruchamiać Satellite (Mikrofon) automatycznie?", default=current_cfg.get("autostart_satellite", False)).ask()
    
    settings = {
        "instance_name": instance_name,
        "room": room,
        "controller_url": controller_url_input,
        "active_tier": active_tier,
        "worker_port": current_cfg.get("worker_port", 8001),
        "worker_host": current_cfg.get("worker_host", "0.0.0.0"),
        "autostart_worker": run_worker,
        "autostart_satellite": run_satellite
    }
    
    data_dir = "data"
    os.makedirs(data_dir, exist_ok=True)
    settings_path = os.path.join(data_dir, "settings.json")
    
    with open(settings_path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4)
        
    console.print(f"\n[bold green]» Konfiguracja zapisana w {settings_path}[/bold green]")
    console.print("[bold green]» Uruchamianie aplikacji w System Tray...[/bold green]\n")

if __name__ == "__main__":
    run_wizard()
