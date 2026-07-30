import os
import subprocess
import sys
import time
import winreg

import questionary
import requests
from rich.rule import Rule
from rich.panel import Panel

from core import config
from node.ux import console, custom_style
from node.wizard import run_wizard

SERVICE_API = "http://127.0.0.1:8099"
AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "RegisNode"

def get_status():
    status = {
        "service": None,
        "controller": "[info]Sprawdzanie...[/info]"
    }
    try:
        resp = requests.get(f"{SERVICE_API}/status", timeout=0.5)
        status["service"] = resp.json()
    except Exception:
        status["service"] = None
        
    settings = config.load_settings()
    server_url = settings.get("server_url", settings.get("controller_url", "http://127.0.0.1:8000"))

    if server_url == "auto":
        from core.discovery import discover_controller
        try:
            server_url = discover_controller()
        except Exception:
            status["controller"] = "[error]OFFLINE[/error] (Auto-Discovery zawiodło)"
            return status
            
    try:
        requests.get(f"{server_url}/docs", timeout=0.5)
        status["controller"] = f"[success]ONLINE[/success] ({server_url})"
    except Exception:
        status["controller"] = "[error]OFFLINE[/error] (Brak połączenia)"
        
    return status

def _service_post(path: str) -> bool:
    try:
        resp = requests.post(f"{SERVICE_API}{path}", timeout=10.0)
        if resp.status_code == 400:
            return False
        return True
    except Exception:
        return False

def is_autostart_enabled():
    if sys.platform != "win32":
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False

def toggle_autostart():
    if sys.platform != "win32":
        return
    enabled = is_autostart_enabled()
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        if enabled:
            winreg.DeleteValue(key, APP_NAME)
        else:
            path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".venv", "Scripts", "pythonw.exe"))
            if os.path.exists(path):
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{path}" -m node.service')
        winreg.CloseKey(key)
    except Exception as e:
        console.print(f"[error]Błąd zmiany autostartu: {e}[/error]")
        time.sleep(2)

def start_service():
    """Uruchamia usługę w tle jako niezależny proces."""
    cmd = [sys.executable, "-m", "node.service"]
        
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        
    subprocess.Popen(cmd, **kwargs)
    console.print("[info]Uruchamianie usługi w tle...[/info]")
    time.sleep(1.0)

def print_header(status: dict):
    os.system("cls" if os.name == "nt" else "clear")
    console.print(Panel.fit("Regis Node — Panel Kontrolny", style="bold cyan"))

    controller_status = status["controller"]
    service = status["service"]

    if service is None:
        console.print(f"Status usługi Węzła: [error]OFF[/error]")
        console.print(f"Kontroler API:       {controller_status}\n")
    else:
        worker_str = "[success]ON[/success]" if service.get("worker") == "running" else "[error]OFF[/error]"
        satellite_str = "[success]ON[/success]" if service.get("satellite") == "running" else "[error]OFF[/error]"
        
        console.print(f"Status usługi Węzła: [success]ON (Działa w tle)[/success]")
        console.print(f"Worker (LLM):        {worker_str}")
        console.print(f"Satellite (Audio):   {satellite_str}")
        console.print(f"Kontroler API:       {controller_status}\n")

def run_dashboard():
    try:
        last_choice_title = None
        
        while True:
            status = get_status()
            service_running = status["service"] is not None
            
            print_header(status)
            
            autostart_action = "Wyłącz autostart przy logowaniu (Windows)" if is_autostart_enabled() else "Włącz autostart przy logowaniu (Windows)"
            
            if service_running:
                worker_action = "Zatrzymaj Worker" if status["service"]["worker"] == "running" else "Uruchom Worker"
                satellite_action = "Zatrzymaj Satellite" if status["service"]["satellite"] == "running" else "Uruchom Satellite"
                
                choices = [
                    "Odśwież status",
                    questionary.Separator(),
                    worker_action,
                    satellite_action,
                    autostart_action,
                    questionary.Separator(),
                    "Konfiguracja...",
                    "Monitor (LLM)",
                    "Monitor Głosowy",
                    questionary.Separator(),
                    "Zatrzymaj usługę w tle",
                    "Wyjście"
                ]
            else:
                choices = [
                    "Odśwież status",
                    questionary.Separator(),
                    questionary.Choice("Uruchom/Zatrzymaj Worker", disabled="usługa główna jest wyłączona"),
                    questionary.Choice("Uruchom/Zatrzymaj Satellite", disabled="usługa główna jest wyłączona"),
                    autostart_action,
                    questionary.Separator(),
                    "Konfiguracja...",
                    "Monitor (LLM)",
                    "Monitor Głosowy",
                    questionary.Separator(),
                    "Uruchom usługę w tle",
                    "Wyjście"
                ]
                
            default_choice = None
            if last_choice_title:
                for c in choices:
                    if isinstance(c, questionary.Separator) or getattr(c, "disabled", None):
                        continue
                    title = c.title if isinstance(c, questionary.Choice) else c
                    if title == last_choice_title or ("Worker" in last_choice_title and "Worker" in title) or ("Satellite" in last_choice_title and "Satellite" in title) or ("autostart" in last_choice_title and "autostart" in title):
                        default_choice = c
                        break
                        
            if default_choice is None or (isinstance(default_choice, questionary.Choice) and default_choice.disabled):
                for c in choices:
                    if not isinstance(c, questionary.Separator) and not getattr(c, "disabled", None):
                        default_choice = c
                        break
                        
            choice = questionary.select(
                "Wybierz akcję:", 
                choices=choices, 
                style=custom_style,
                instruction=" ",
                qmark="",
                default=default_choice,
                erase_when_done=True
            ).ask()
            
            if not choice or choice == "Wyjście":
                break
                
            last_choice_title = choice
            
            if choice == "Uruchom Worker":
                success = _service_post("/worker/toggle")
                if not success:
                    console.print("\n[error]Błąd: Nie można uruchomić Workera! Sprawdź czy Ollama jest włączona.[/error]")
                    time.sleep(2)
            elif choice == "Zatrzymaj Worker":
                console.print("\n[dim]Zatrzymywanie Workera i zwalnianie pamięci VRAM...[/dim]")
                _service_post("/worker/toggle")
            elif choice in ("Uruchom Satellite", "Zatrzymaj Satellite"):
                _service_post("/satellite/toggle")
            elif choice == "Uruchom usługę w tle":
                start_service()
            elif choice == "Zatrzymaj usługę w tle":
                _service_post("/shutdown")
                time.sleep(0.5)
            elif "autostart przy logowaniu" in choice:
                toggle_autostart()
            elif choice == "Konfiguracja...":
                os.system("cls" if os.name == "nt" else "clear")
                run_wizard()
                
                # Zresetowanie pracujących usług
                if service_running:
                    if status["service"].get("worker") == "running":
                        _service_post("/worker/toggle")
                        time.sleep(1.0)
                        _service_post("/worker/toggle")
                    if status["service"].get("satellite") == "running":
                        _service_post("/satellite/toggle")
                        time.sleep(1.0)
                        _service_post("/satellite/toggle")
                    
                    console.print("[dim]Przeładowano pracujące usługi z nową konfiguracją...[/dim]")
                    time.sleep(1.5)
            elif choice == "Monitor (LLM)":
                os.system("cls" if os.name == "nt" else "clear")
                from node.monitor import dev_chat
                dev_chat()
            elif choice == "Monitor Głosowy":
                os.system("cls" if os.name == "nt" else "clear")
                from node.monitor_voice import run_voice_monitor
                run_voice_monitor()
                
    except KeyboardInterrupt:
        pass
    finally:
        os.system("cls" if os.name == "nt" else "clear")
        console.print("[info]Zakończono pracę Panelu Kontrolnego.[/info]\n")

if __name__ == "__main__":
    run_dashboard()
