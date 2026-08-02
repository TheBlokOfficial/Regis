import sys
import os
import json
import subprocess
import webbrowser
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import threading
import time
import socketserver
import queue as _q
from collections import deque
from http.server import BaseHTTPRequestHandler
import psutil
import atexit
import signal
from core.config import DATA_DIR

import asyncio
import websockets

_ws_loop = None
_ws_client = None

def _bus_publish(event: dict) -> None:
    """Wysyła zdarzenie bezpośrednio przez otwarty WebSocket do Kontrolera."""
    if "timestamp" not in event:
        event["timestamp"] = time.strftime("%H:%M:%S")
    
    if _ws_loop and _ws_client:
        payload = json.dumps({
            "type": "satellite_event",
            "event_type": event.get("type", "unknown"),
            "data": event
        }, ensure_ascii=False)
        asyncio.run_coroutine_threadsafe(_ws_client.send(payload), _ws_loop)

worker_process = None
satellite_process = None
tray_icon = None

_settings_lock = threading.Lock()

def get_settings():
    with _settings_lock:
        settings_path = os.path.join("data", "settings.json")
        if os.path.exists(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}


def save_settings(settings_dict: dict) -> None:
    with _settings_lock:
        os.makedirs("data", exist_ok=True)
        settings_path = os.path.join("data", "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings_dict, f, indent=4, ensure_ascii=False)


def _is_model_present_locally(model_name: str) -> bool:
    try:
        import requests
        settings = get_settings()
        ollama_url = settings.get("ollama_url", "http://127.0.0.1:11434")
        resp = requests.get(f"{ollama_url}/api/tags", timeout=3.0)
        if resp.ok:
            models = [m.get("name") for m in resp.json().get("models", [])]
            return any(model_name in m or m in model_name for m in models)
    except Exception:
        pass
    return False

def _ensure_ollama_model(model_name: str, start_after: bool = False) -> None:
    """Sprawdza w lokalnej Ollamie czy model jest pobrany; jeśli nie, dociąga w tle."""
    def _do_pull():
        try:
            import requests
            settings = get_settings()
            ollama_url = settings.get("ollama_url", "http://127.0.0.1:11434")

            if _is_model_present_locally(model_name):
                if start_after and not is_worker_running():
                    start_worker()
                return

            print(f"[Ollama Pull] Rozpoczynam pobieranie modelu '{model_name}'...")
            requests.post(f"{ollama_url}/api/pull", json={"name": model_name}, timeout=600)
            print(f"[Ollama Pull] Model '{model_name}' pobrany pomyślnie.")
            if start_after and not is_worker_running():
                start_worker()
        except Exception as e:
            print(f"[Ollama Pull] Błąd pobierania modelu '{model_name}': {e}")

    threading.Thread(target=_do_pull, daemon=True).start()


def _apply_node_config(config_data: dict, from_registration: bool = False) -> None:
    settings = get_settings()

    if "name" in config_data:
        settings["instance_name"] = config_data["name"]

    services = config_data.get("services", {})

    # 1. Konfiguracja Workera (LLM)
    if "worker" in services:
        w_cfg = services["worker"]
        needs_pull = False
        if "model_name" in w_cfg:
            settings["selected_model"] = w_cfg["model_name"]
            needs_pull = not _is_model_present_locally(w_cfg["model_name"])
        if "priority" in w_cfg:
            settings["worker_priority"] = w_cfg["priority"]
        settings["autostart_worker"] = True
        
        if needs_pull:
            _ensure_ollama_model(w_cfg["model_name"], start_after=True)
        else:
            if not is_worker_running():
                start_worker()
    else:
        settings["autostart_worker"] = False
        if is_worker_running():
            stop_worker()

    # 2. Konfiguracja Satelity (Audio/VAD)
    if "satellite" in services:
        s_cfg = services["satellite"]
        if "room" in s_cfg:
            settings["room"] = s_cfg["room"]
        settings["autostart_satellite"] = True
        if not is_satellite_running():
            start_satellite()
    else:
        settings["autostart_satellite"] = False
        if is_satellite_running():
            stop_satellite()

    save_settings(settings)
    if not from_registration:
        register_node_with_controller()

def create_default_icon():
    # Tworzenie prostej kwadratowej ikony 64x64
    image = Image.new('RGB', (64, 64), color=(40, 40, 40))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(0, 120, 215))
    return image

def get_executable_command(module_name):
    venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".venv", "Scripts", "python.exe"))
    exe = venv_python if os.path.exists(venv_python) else sys.executable
    return [exe, "-m", f"node.{module_name}"]

def _kill_process_tree(pid: int) -> None:
    try:
        parent = psutil.Process(pid)
        for child in parent.children(recursive=True):
            try:
                child.kill()
            except psutil.NoSuchProcess:
                pass
        parent.kill()
    except psutil.NoSuchProcess:
        pass

def _assign_to_job_object(proc) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]
                        
        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [("ReadOperationCount", ctypes.c_uint64),
                        ("WriteOperationCount", ctypes.c_uint64),
                        ("OtherOperationCount", ctypes.c_uint64),
                        ("ReadTransferCount", ctypes.c_uint64),
                        ("WriteTransferCount", ctypes.c_uint64),
                        ("OtherTransferCount", ctypes.c_uint64)]
                        
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]
                        
        job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        
        ctypes.windll.kernel32.SetInformationJobObject(
            job, 9, ctypes.pointer(info), ctypes.sizeof(info)
        )
        
        # 0x1F0FFF = PROCESS_ALL_ACCESS
        hProcess = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, proc.pid)
        if hProcess:
            ctypes.windll.kernel32.AssignProcessToJobObject(job, hProcess)
            ctypes.windll.kernel32.CloseHandle(hProcess)
            # Zatrzymujemy uchwyt joba by Windows go nie zniszczył przedwcześnie
            proc._win_job_handle = job
    except Exception as e:
        print(f"Błąd przypisywania procesu do Job Object: {e}")

def _cleanup_orphaned_processes() -> None:
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()
            if "python" in (proc.info.get('name') or "").lower() or "python" in cmd_str:
                if "node.satellite" in cmd_str or "node.node" in cmd_str:
                    print(f"[Cleanup] Uśmiercanie starego procesu-sieroty: PID {proc.info['pid']} ({cmd_str})")
                    _kill_process_tree(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


def start_worker():
    global worker_process
    if worker_process is None or worker_process.poll() is not None:
        try:
            import requests
            settings = get_settings()
            requests.get(f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/tags", timeout=1.5)
        except Exception as e:
            print(f"Ollama offline, nie uruchamiam workera: {e}")
            return False

        cmd = get_executable_command("node")
        kwargs = {}
        
        os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)
        log_path = os.path.join(DATA_DIR, "logs", "worker.log")
        f = open(log_path, "a", encoding="utf-8")
        kwargs["stdout"] = f
        kwargs["stderr"] = subprocess.STDOUT
        
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
        worker_process = subprocess.Popen(cmd, **kwargs)
        _assign_to_job_object(worker_process)
        return True
    return True

def stop_worker():
    global worker_process
    if worker_process is not None:
        try:
            import requests
            settings = get_settings()
            port = settings.get("worker_port", 8001)
            requests.post(f"http://127.0.0.1:{port}/v1/system/shutdown", timeout=5)
        except Exception:
            pass
        _kill_process_tree(worker_process.pid)
        worker_process = None

def start_satellite():
    global satellite_process
    if satellite_process is None or satellite_process.poll() is not None:
        cmd = get_executable_command("satellite")
        kwargs = {}
        
        os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)
        log_path = os.path.join(DATA_DIR, "logs", "satellite.log")
        f = open(log_path, "a", encoding="utf-8")
        kwargs["stdout"] = f
        kwargs["stderr"] = subprocess.STDOUT
        
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
            
        satellite_process = subprocess.Popen(cmd, env=env, **kwargs)
        _assign_to_job_object(satellite_process)
        return True
    return True

def stop_satellite():
    global satellite_process
    if satellite_process is not None:
        _kill_process_tree(satellite_process.pid)
        satellite_process = None

def is_worker_running():
    return worker_process is not None and worker_process.poll() is None

def is_satellite_running():
    return satellite_process is not None and satellite_process.poll() is None

def register_node_with_controller():
    """Wysyła zbiorczą rejestrację Zjednoczonego Węzła do Kontrolera."""
    def _do_reg():
        try:
            import requests
            from core.discovery import discover_controller, get_local_ip
            
            settings = get_settings()
            node_id = settings.get("instance_name", settings.get("satellite_id", "RTX-5070"))
            controller_url = settings.get("controller_url", "auto")
            if controller_url == "auto":
                try:
                    controller_url = discover_controller()
                except Exception:
                    controller_url = "http://192.168.0.119:8000"
                    
            services_dict = {}
            if is_worker_running() or settings.get("autostart_worker"):
                services_dict["worker"] = {
                    "model_name": settings.get("selected_model", "qwen3.5:9b"),
                    "priority": settings.get("worker_priority", 100),
                }
            if is_satellite_running() or settings.get("autostart_satellite"):
                services_dict["satellite"] = {
                    "room": settings.get("room", "pracownia_glowna"),
                    "node_type": "desktop",
                    "capabilities": ["audio_input", "tts_output", "wakeword"],
                    "wakeword_local": True,
                }

            payload = {
                "id": node_id,
                "name": settings.get("instance_name", node_id),
                "host": get_local_ip(),
                "port": 8099,
                "services": services_dict,
            }
            resp = requests.post(f"{controller_url}/v1/nodes/register", json=payload, timeout=5)
            resp.raise_for_status()
            print(f"Zjednoczony Węzeł '{node_id}' zarejestrowany w Kontrolerze ({controller_url}).")
            
            config_data = resp.json().get("config")
            if config_data:
                _apply_node_config(config_data, from_registration=True)
                
        except Exception as e:
            print(f"Nie udało się zarejestrować Węzła w Kontrolerze: {e}")

    threading.Thread(target=_do_reg, daemon=True).start()

def unregister_node_with_controller():
    try:
        import requests
        from core.discovery import discover_controller
        settings = get_settings()
        node_id = settings.get("instance_name", settings.get("satellite_id", "RTX-5070"))
        controller_url = settings.get("controller_url", "auto")
        if controller_url == "auto":
            try:
                controller_url = discover_controller()
            except Exception:
                controller_url = "http://192.168.0.119:8000"
        requests.delete(f"{controller_url}/v1/nodes/{node_id}", timeout=2)
        print(f"Wyrejestrowano Zjednoczony Węzeł '{node_id}' z Kontrolera.")
    except Exception:
        pass

async def _ws_client_loop():
    global _ws_client
    settings = get_settings()
    node_id = settings.get("instance_name", settings.get("satellite_id", "RTX-5070"))
    controller_url = settings.get("controller_url", "auto")
    if controller_url == "auto":
        try:
            from core.discovery import discover_controller
            controller_url = discover_controller()
        except Exception:
            controller_url = "http://192.168.0.119:8000"
            
    ws_url = controller_url.replace("http://", "ws://").replace("https://", "wss://") + f"/v1/ws/nodes/{node_id}"
    
    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                _ws_client = ws
                print(f"Połączono z Kontrolerem przez WebSocket ({ws_url}).")
                
                async for message in ws:
                    try:
                        data = json.loads(message)
                        cmd = data.get("command")
                        payload = data.get("data", {})
                        
                        if cmd == "config":
                            _apply_node_config(payload, from_registration=True)
                            await ws.send(json.dumps({"type": "command_result", "command": cmd, "success": True}))
                        elif cmd == "worker_start":
                            success = start_worker()
                            await ws.send(json.dumps({"type": "command_result", "command": cmd, "success": success}))
                        elif cmd == "worker_stop":
                            stop_worker()
                            await ws.send(json.dumps({"type": "command_result", "command": cmd, "success": True}))
                        elif cmd == "satellite_start":
                            start_satellite()
                            await ws.send(json.dumps({"type": "command_result", "command": cmd, "success": True}))
                        elif cmd == "satellite_stop":
                            stop_satellite()
                            await ws.send(json.dumps({"type": "command_result", "command": cmd, "success": True}))
                        elif cmd == "status":
                            await ws.send(json.dumps({
                                "type": "command_result", 
                                "command": cmd, 
                                "success": True, 
                                "result": {
                                    "worker": "running" if is_worker_running() else "stopped",
                                    "satellite": "running" if is_satellite_running() else "stopped",
                                    "autostart_worker": get_settings().get("autostart_worker", False),
                                    "autostart_satellite": get_settings().get("autostart_satellite", False),
                                }
                            }))
                    except Exception as e:
                        print(f"Błąd przetwarzania komendy WS: {e}")
        except Exception as e:
            _ws_client = None
            print(f"Rozłączono z Kontrolerem. Ponawiam za 5s... ({e})")
            await asyncio.sleep(5)

def _start_ws_client():
    global _ws_loop
    _ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_loop)
    _ws_loop.run_until_complete(_ws_client_loop())

def open_dashboard():
    settings = get_settings()
    server_url = settings.get("server_url", settings.get("controller_url", "http://127.0.0.1:8000"))
    if server_url == "auto":
        try:
            from core.discovery import discover_controller
            server_url = discover_controller()
        except Exception:
            server_url = "http://127.0.0.1:8000"
    webbrowser.open(server_url)

def quit_all(icon=None, item=None):
    stop_worker()
    stop_satellite()
    unregister_node_with_controller()
    if tray_icon:
        tray_icon.stop()
    elif icon:
        icon.stop()
    os._exit(0)

def get_menu():
    settings = get_settings()
    name = settings.get("instance_name", "Regis Node")
    return pystray.Menu(
        item(lambda text: f"Regis Node — {name}", lambda: None, enabled=False),
        pystray.Menu.SEPARATOR,
        item("Otwórz panel kontrolny", lambda: open_dashboard()),
        pystray.Menu.SEPARATOR,
        item("Zamknij", quit_all),
    )


def run_service():
    global tray_icon
    
    # 1. Bezwzględne czyszczenie wszystkich starych podprocesów-sierot z poprzednich awarii
    _cleanup_orphaned_processes()
    
    # 2. Rejestracja globalnego hooka atexit i sygnałów (zabije podprocesy przy dowolnym stopie)
    atexit.register(quit_all)
    try:
        signal.signal(signal.SIGTERM, lambda signum, frame: quit_all())
        signal.signal(signal.SIGINT, lambda signum, frame: quit_all())
    except ValueError:
        pass # Ignoruj jeśli nie jesteśmy w głównym wątku

    settings = get_settings()
    if settings.get("autostart_worker"):
        def _autostart_with_retry():
            import time
            for _ in range(30):
                if start_worker():
                    print("Autostart: Worker uruchomiony pomyślnie.")
                    break
                print("Autostart: Ollama niedostępna, ponawiam za 2 sekundy...")
                time.sleep(2)
        
        import threading
        threading.Thread(target=_autostart_with_retry, daemon=True).start()

    if settings.get("autostart_satellite"):
        start_satellite()

    # Rejestracja Zjednoczonego Węzła z Kontrolerem
    register_node_with_controller()

    tray_icon = pystray.Icon("node", create_default_icon(), "Regis Node", menu=get_menu())
    
    ws_thread = threading.Thread(target=_start_ws_client, daemon=True)
    ws_thread.start()

    tray_icon.run()

if __name__ == "__main__":
    run_service()
