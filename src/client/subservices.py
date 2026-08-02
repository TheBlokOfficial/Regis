import os
import sys
import subprocess

from client.config import DATA_DIR, load_settings
from client.proc_utils import get_executable_command, kill_process_tree, assign_to_job_object


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
        model = config_data.get("model_name", "qwen3.5:9b")
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
        return {
            "model_name": getattr(self, "model", "qwen3.5:9b"),
            "priority": 100,
        }


class SatelliteSubservice(BaseSubservice):
    def __init__(self):
        super().__init__("satellite", "services.satellite", "satellite.log")

    def get_command_args(self, config_data: dict) -> list[str]:
        room = config_data.get("room", "salon")
        self.room = room
        return ["--room", room]

    def get_registration_payload(self) -> dict | None:
        if not self.is_running():
            return None
        return {
            "room": getattr(self, "room", "salon"),
            "node_type": "desktop",
            "capabilities": ["audio_input", "tts_output", "wakeword"],
            "wakeword_local": True,
        }
