import os
import json
import socket
import requests
import questionary

from client.legacy.ux import console
from rich.rule import Rule
from protocol.discovery import discover_controller
from client.config import load_settings

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
    
    # Wybór modelu z Ollamy
    console.print("[dim]Pobieranie zainstalowanych modeli z Ollamy...[/dim]")
    ollama_url = current_cfg.get("ollama_url", "http://127.0.0.1:11434")
    available_models = []
    try:
        resp = requests.get(f"{ollama_url}/api/tags", timeout=3)
        if resp.ok:
            available_models = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        pass

    saved_model = current_cfg.get("selected_model", "qwen3.5:9b")
    if available_models:
        model_choices = available_models + ["[Wpisz ręcznie inny model]"]
        default_model_idx = 0
        if saved_model in available_models:
            default_model_idx = available_models.index(saved_model)
        else:
            default_model_idx = len(model_choices) - 1

        selected_model_choice = questionary.select(
            "Wybierz model LLM zainstalowany w Ollamie:",
            choices=model_choices,
            default=model_choices[default_model_idx]
        ).ask()

        if selected_model_choice == "[Wpisz ręcznie inny model]" or not selected_model_choice:
            selected_model = questionary.text(
                "Wpisz własną nazwę modelu w Ollamie:",
                default=saved_model
            ).ask()
        else:
            selected_model = selected_model_choice
    else:
        console.print("[bold yellow]Ostrzeżenie: Nie udało się pobrać modeli z Ollamy (czy usługa Ollama jest włączona?).[/bold yellow]")
        selected_model = questionary.text(
            "Wpisz nazwę modelu w Ollamie (np. qwen3.5:9b):",
            default=saved_model
        ).ask()

    # Priorytet węzła
    priority_input = questionary.text(
        "Priorytet tego Węzła (wyższa liczba = ważniejszy, np. 100 = GPU PC, 10 = RPi):",
        default=str(current_cfg.get("worker_priority", 100))
    ).ask()

    try:
        worker_priority = int(priority_input)
    except (ValueError, TypeError):
        worker_priority = 100

    print("\nUsługi w tle:")
    run_worker = questionary.confirm("Uruchamiać Worker (LLM) automatycznie?", default=current_cfg.get("autostart_worker", True)).ask()
    run_satellite = questionary.confirm("Uruchamiać Satellite (Mikrofon) automatycznie?", default=current_cfg.get("autostart_satellite", False)).ask()
    
    settings = {
        "instance_name": instance_name,
        "room": room,
        "controller_url": controller_url_input,
        "selected_model": selected_model,
        "worker_priority": worker_priority,
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
