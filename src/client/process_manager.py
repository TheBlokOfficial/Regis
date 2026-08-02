import os
import sys
import subprocess
from protocol.schemas import ServiceAction
from client.proc_utils import cleanup_orphaned_processes, get_executable_command, kill_process_tree, assign_to_job_object
from client.config import DATA_DIR, load_settings

_active_processes: dict[str, subprocess.Popen] = {}
_service_configs: dict[str, dict] = {}

def control_service(name: str, action: ServiceAction | str, config_data: dict = None) -> bool:
    """Zarządza stanem usługi (start, stop, restart)."""
    act = action if isinstance(action, ServiceAction) else ServiceAction(action)

    match act:
        case ServiceAction.START:
            return _start_service(name, config_data)
        case ServiceAction.STOP:
            return _stop_service(name)
        case ServiceAction.RESTART:
            _stop_service(name)
            return _start_service(name, config_data)
        case _:
            return False

def _start_service(name: str, config_data: dict = None) -> bool:
    if name in _active_processes and _active_processes[name].poll() is None:
        return True # already running

    config_data = config_data or {}
    _service_configs[name] = config_data
    
    cmd = get_executable_command(f"services.{name}")
    
    # Budowanie argumentów na podstawie nazwy usługi (zamiast polimorfizmu Subservice)
    if name == "worker":
        settings = load_settings()
        model = config_data.get("model_name", settings.get("selected_model", "qwen3.5:9b"))
        port = config_data.get("port", settings.get("worker_port", 8001))
        cmd.extend(["--model", model, "--port", str(port)])
    elif name == "satellite":
        room = config_data.get("room", "salon")
        cmd.extend(["--room", room])

    kwargs = {}
    os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)
    log_path = os.path.join(DATA_DIR, "logs", f"{name}.log")
    f = open(log_path, "a", encoding="utf-8")
    kwargs["stdout"] = f
    kwargs["stderr"] = subprocess.STDOUT

    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    try:
        proc = subprocess.Popen(cmd, env=env, **kwargs)
        assign_to_job_object(proc)
        _active_processes[name] = proc
        return True
    except Exception as e:
        print(f"Błąd uruchamiania usługi {name}: {e}")
        return False

def _stop_service(name: str) -> bool:
    if name in _active_processes:
        proc = _active_processes[name]
        
        # Shutdown hook dla workera
        if name == "worker":
            try:
                import requests
                settings = load_settings()
                port = _service_configs.get("worker", {}).get("port", settings.get("worker_port", 8001))
                requests.post(f"http://127.0.0.1:{port}/v1/system/shutdown", timeout=5)
            except Exception:
                pass
                
        kill_process_tree(proc.pid)
        del _active_processes[name]
    return True

def stop_all_services() -> None:
    for name in list(_active_processes.keys()):
        _stop_service(name)

def get_all_services_status() -> dict:
    status = {}
    for name in ["worker", "satellite"]:
        if name in _active_processes and _active_processes[name].poll() is None:
            status[name] = "running"
        else:
            status[name] = "stopped"
    return status
    
def get_active_services_registration() -> dict:
    reg = {}
    
    if "worker" in _active_processes and _active_processes["worker"].poll() is None:
        settings = load_settings()
        cfg = _service_configs.get("worker", {})
        reg["worker"] = {
            "model_name": cfg.get("model_name", settings.get("selected_model", "qwen3.5:9b")),
            "priority": 100
        }
        
    if "satellite" in _active_processes and _active_processes["satellite"].poll() is None:
        cfg = _service_configs.get("satellite", {})
        reg["satellite"] = {
            "room": cfg.get("room", "salon"),
            "node_type": "desktop",
            "capabilities": ["audio_input", "tts_output", "wakeword"],
            "wakeword_local": True
        }
        
    return reg
