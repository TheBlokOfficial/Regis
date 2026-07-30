import sys
import os
import json
import subprocess
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageDraw
import threading
import time
import socketserver
import queue as _q
from collections import deque
from http.server import BaseHTTPRequestHandler
from core.config import DATA_DIR

# ─── Event Bus (satelita → monitor głosowy) ───────────────────────────────────
_event_history: deque = deque(maxlen=200)
_event_subscribers: list[_q.Queue] = []
_event_subscribers_lock = threading.Lock()


def _bus_publish(event: dict) -> None:
    """Wrzuca event do historii i rozsyła do wszystkich aktywnych subskrybentów SSE."""
    with _event_subscribers_lock:
        _event_history.append(event)
        for sub in _event_subscribers:
            try:
                sub.put_nowait(event)
            except _q.Full:
                pass

worker_process = None
satellite_process = None
tray_icon = None

def get_settings():
    settings_path = os.path.join("data", "settings.json")
    if os.path.exists(settings_path):
        with open(settings_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def create_default_icon():
    # Tworzenie prostej kwadratowej ikony 64x64
    image = Image.new('RGB', (64, 64), color=(40, 40, 40))
    dc = ImageDraw.Draw(image)
    dc.rectangle((16, 16, 48, 48), fill=(0, 120, 215))
    return image

def get_executable_command(module_name=None):
    venv_python = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".venv", "Scripts", "python.exe"))
    exe = venv_python if os.path.exists(venv_python) else sys.executable
    if module_name:
        return [exe, "-m", f"node.{module_name}"]
    return [exe, "-m", "node.dashboard"]

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
        worker_process.terminate()
        worker_process.wait()
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

def stop_satellite():
    global satellite_process
    if satellite_process is not None:
        satellite_process.terminate()
        satellite_process.wait()
        satellite_process = None

def is_worker_running():
    return worker_process is not None and worker_process.poll() is None

def is_satellite_running():
    return satellite_process is not None and satellite_process.poll() is None

MANAGEMENT_PORT = 8099

class _ServiceHandler(BaseHTTPRequestHandler):
    """Minimalistyczny HTTP handler dla API zarządzania usługą."""

    def log_message(self, format, *args):
        pass  # wycisz logi HTTP w konsoli

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_sse(self):
        """Obsługuje long-lived SSE połączenie. Blokuje wątek do rozłączenia klienta."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        sub: _q.Queue = _q.Queue(maxsize=500)

        with _event_subscribers_lock:
            # Odtwórz historię dla nowego klienta
            for past_event in _event_history:
                data = json.dumps(past_event, ensure_ascii=False)
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
            self.wfile.flush()
            _event_subscribers.append(sub)

        try:
            while True:
                try:
                    event = sub.get(timeout=15)
                    data = json.dumps(event, ensure_ascii=False)
                    self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    self.wfile.flush()
                except _q.Empty:
                    # Heartbeat co 15s — utrzymuje połączenie
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with _event_subscribers_lock:
                try:
                    _event_subscribers.remove(sub)
                except ValueError:
                    pass

    def do_GET(self):
        if self.path == "/status":
            self._send_json({
                "worker": "running" if is_worker_running() else "stopped",
                "satellite": "running" if is_satellite_running() else "stopped",
                "autostart_worker": get_settings().get("autostart_worker", False),
                "autostart_satellite": get_settings().get("autostart_satellite", False),
            })
        elif self.path == "/satellite/events":
            self._handle_sse()
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        if self.path == "/worker/toggle":
            if is_worker_running():
                stop_worker()
                self._send_json({"worker": "stopped"})
            else:
                success = start_worker()
                if not success:
                    self._send_json({"error": "Ollama is offline"}, 400)
                    return
                self._send_json({"worker": "running"})

        elif self.path == "/satellite/toggle":
            if is_satellite_running():
                stop_satellite()
            else:
                start_satellite()
            self._send_json({"satellite": "running" if is_satellite_running() else "stopped"})

        elif self.path == "/satellite/event":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                event = json.loads(body)
                _bus_publish(event)
                self._send_json({"ok": True})
            except Exception:
                self._send_json({"error": "invalid json"}, 400)

        elif self.path == "/shutdown":
            self._send_json({"status": "shutting_down"})
            # Dajemy chwilę na odesłanie odpowiedzi, potem zamykamy
            threading.Thread(target=lambda: (time.sleep(0.5), quit_all(None, None))).start()

        else:
            self._send_json({"error": "not found"}, 404)


def _start_management_server(server):
    """Uruchamia serwer zarządzania w tle (daemon thread)."""
    server.serve_forever()

def open_dashboard():
    cmd = get_executable_command(None)
    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)

def quit_all(icon=None, item=None):
    stop_worker()
    stop_satellite()
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
    try:
        # ThreadingTCPServer — każde połączenie dostaje własny wątek.
        # Wymagane dla SSE (long-lived connections), które blokowałyby TCPServer.
        server = socketserver.ThreadingTCPServer(("127.0.0.1", MANAGEMENT_PORT), _ServiceHandler)
        server.allow_reuse_address = True
    except OSError:
        print(f"Usługa Regis Node działa już w tle (port {MANAGEMENT_PORT} zajęty).")
        sys.exit(0)
        
    global tray_icon
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

    tray_icon = pystray.Icon("node", create_default_icon(), "Regis Node", menu=get_menu())
    
    mgmt_thread = threading.Thread(target=_start_management_server, args=(server,), daemon=True)
    mgmt_thread.start()
    

    tray_icon.run()

if __name__ == "__main__":
    run_service()
