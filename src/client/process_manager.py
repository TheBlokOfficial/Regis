import sys
import os
import subprocess
import psutil
from typing import Any
from client.config import DATA_DIR, load_settings

def get_executable_command(module_name: str) -> list[str]:
    """Buduje polecenie uruchomienia podmodułu w środowisku venv Pythona (Windows / Linux / macOS)."""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    venv_win = os.path.join(base_dir, ".venv", "Scripts", "python.exe")
    venv_nix = os.path.join(base_dir, ".venv", "bin", "python")

    if os.path.exists(venv_win):
        exe = venv_win
    elif os.path.exists(venv_nix):
        exe = venv_nix
    else:
        exe = sys.executable
    return [exe, "-m", f"node.{module_name}"]

def kill_process_tree(pid: int) -> None:
    """Uśmierca cały drzewo procesów o podanym PID."""
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

def assign_to_job_object(proc: subprocess.Popen) -> None:
    """Przypisuje proces do Job Object w systemie Windows (auto-kill przy zamknięciu)."""
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
        
        hProcess = ctypes.windll.kernel32.OpenProcess(0x1F0FFF, False, proc.pid)
        if hProcess:
            ctypes.windll.kernel32.AssignProcessToJobObject(job, hProcess)
            ctypes.windll.kernel32.CloseHandle(hProcess)
            proc._win_job_handle = job
    except Exception as e:
        print(f"Błąd przypisywania procesu do Job Object: {e}")

def cleanup_orphaned_processes() -> None:
    """Czyści porzucone podprocesy z poprzednich awarii."""
    current_pid = os.getpid()
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['pid'] == current_pid:
                continue
            cmdline = proc.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()
            if "python" in (proc.info.get('name') or "").lower() or "python" in cmd_str:
                if "node.services.satellite" in cmd_str or "node.services.worker" in cmd_str or "node.satellite" in cmd_str or "node.node" in cmd_str:
                    print(f"[Cleanup] Uśmiercanie starego procesu-sieroty: PID {proc.info['pid']} ({cmd_str})")
                    kill_process_tree(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


class BaseSubservice:
    """Klasa bazowa do zarządzania życiem pojedynczego podprocesu (usługi) w Węźle."""
    
    def __init__(self, name: str, module_path: str, log_filename: str):
        self.name = name
        self.module_path = module_path
        self.log_filename = log_filename
        self.process: subprocess.Popen | None = None
        self.config: dict = {}

    def get_command_args(self, config_data: dict) -> list[str]:
        """Do nadpisania w podklasach. Powinna zwrócić parametry CLI np. ['--model', 'qwen']."""
        return []

    def before_start(self, config_data: dict) -> bool:
        """Hook uruchamiany przed startem. Zwrócenie False anuluje start."""
        return True

    def start(self, config_data: dict = None) -> bool:
        if self.is_running():
            return True
            
        config_data = config_data or {}
        self.config = config_data
        
        if not self.before_start(config_data):
            return False

        cmd = get_executable_command(self.module_path)
        cmd.extend(self.get_command_args(config_data))

        kwargs = {}
        os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)
        log_path = os.path.join(DATA_DIR, "logs", self.log_filename)
        f = open(log_path, "a", encoding="utf-8")
        kwargs["stdout"] = f
        kwargs["stderr"] = subprocess.STDOUT

        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        try:
            self.process = subprocess.Popen(cmd, env=env, **kwargs)
            assign_to_job_object(self.process)
            return True
        except Exception as e:
            print(f"Błąd uruchamiania usługi {self.name}: {e}")
            return False

    def on_stop(self) -> None:
        """Hook uruchamiany przed twardym ubiciem procesu (np. wysłanie requesta shutdown)."""
        pass

    def stop(self) -> None:
        if self.process is not None:
            self.on_stop()
            kill_process_tree(self.process.pid)
            self.process = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None
        
    def get_status_payload(self) -> str:
        return "running" if self.is_running() else "stopped"
        
    def get_registration_payload(self) -> dict | None:
        """Dane do rejestracji w Kontrolerze. Nadpisane przez podklasę."""
        return None


class WorkerSubservice(BaseSubservice):
    def __init__(self):
        super().__init__("worker", "services.worker", "worker.log")

    def start(self, config_data: dict = None) -> bool:
        if self.is_running():
            return True
            
        config_data = config_data or {}
        settings = load_settings()
        model = config_data.get("model_name") or settings.get("selected_model", "qwen3.5:9b")
        
        if self._has_model(model):
            return super().start(config_data)
            
        import threading
        threading.Thread(target=self._ensure_model_and_start, args=(model, config_data), daemon=True).start()
        return True

    def _has_model(self, model_name: str) -> bool:
        try:
            import requests
            settings = load_settings()
            ollama_url = settings.get("ollama_url", "http://127.0.0.1:11434")
            resp = requests.get(f"{ollama_url}/api/tags", timeout=3.0)
            if resp.ok:
                models = [m.get("name") for m in resp.json().get("models", [])]
                return any(model_name in m or m in model_name for m in models)
        except Exception:
            pass
        return False

    def _ensure_model_and_start(self, model_name: str, config_data: dict) -> None:
        try:
            import requests
            settings = load_settings()
            ollama_url = settings.get("ollama_url", "http://127.0.0.1:11434")
            print(f"[Ollama Pull] Rozpoczynam pobieranie modelu '{model_name}'...")
            requests.post(f"{ollama_url}/api/pull", json={"name": model_name}, timeout=600)
            print(f"[Ollama Pull] Model '{model_name}' pobrany pomyślnie.")
            super().start(config_data)
        except Exception as e:
            print(f"[Ollama Pull] Błąd pobierania modelu '{model_name}': {e}")

    def before_start(self, config_data: dict) -> bool:
        try:
            import requests
            settings = load_settings()
            requests.get(f"{settings.get('ollama_url', 'http://127.0.0.1:11434')}/api/tags", timeout=1.5)
        except Exception as e:
            print(f"Ollama offline, nie uruchamiam workera: {e}")
            return False
        return True

    def get_command_args(self, config_data: dict) -> list[str]:
        settings = load_settings()
        model = config_data.get("model_name") or settings.get("selected_model", "qwen3.5:9b")
        port = config_data.get("port", settings.get("worker_port", 8001))
        
        # Zapamiętujemy by użyć w shutdown lub rejestracji
        self.port = port
        self.model = model
        
        return ["--model", model, "--port", str(port)]
        
    def on_stop(self) -> None:
        try:
            import requests
            requests.post(f"http://127.0.0.1:{getattr(self, 'port', 8001)}/v1/system/shutdown", timeout=5)
        except Exception:
            pass

    def get_registration_payload(self) -> dict | None:
        if not self.is_running():
            return None
        settings = load_settings()
        return {
            "model_name": getattr(self, "model", settings.get("selected_model", "qwen3.5:9b")),
            "priority": settings.get("worker_priority", 100),
        }


class SatelliteSubservice(BaseSubservice):
    def __init__(self):
        super().__init__("satellite", "services.satellite", "satellite.log")

    def get_command_args(self, config_data: dict) -> list[str]:
        room = config_data.get("room") or load_settings().get("room", "salon")
        self.room = room
        return ["--room", room]

    def get_registration_payload(self) -> dict | None:
        if not self.is_running():
            return None
        return {
            "room": getattr(self, "room", load_settings().get("room", "salon")),
            "node_type": "desktop",
            "capabilities": ["audio_input", "tts_output", "wakeword"],
            "wakeword_local": True,
        }

# Globalny Rejestr
SERVICES: dict[str, BaseSubservice] = {
    "worker": WorkerSubservice(),
    "satellite": SatelliteSubservice(),
}

def start_service(name: str, config_data: dict = None) -> bool:
    if name in SERVICES:
        return SERVICES[name].start(config_data)
    return False

def stop_service(name: str) -> None:
    if name in SERVICES:
        SERVICES[name].stop()

def stop_all_services() -> None:
    for srv in SERVICES.values():
        srv.stop()

def get_all_services_status() -> dict:
    return {name: srv.get_status_payload() for name, srv in SERVICES.items()}
    
def get_active_services_registration() -> dict:
    reg = {}
    for name, srv in SERVICES.items():
        payload = srv.get_registration_payload()
        if payload:
            reg[name] = payload
    return reg
