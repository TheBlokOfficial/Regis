import os
import sys
import subprocess
import json
from protocol.schemas import ServiceAction
from client.proc_utils import cleanup_orphaned_processes, get_executable_command, kill_process_tree, assign_to_job_object
from client.config import DATA_DIR

_active_processes: dict[str, subprocess.Popen] = {}
_service_configs: dict[str, dict] = {}

def control_service(name: str, action: ServiceAction | str, config_data: dict = None) -> bool:
    """Zarządza stanem dowolnej usługi w systemie (start, stop, restart)."""
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
        return True

    config_data = config_data or {}
    _service_configs[name] = config_data
    
    cmd = get_executable_command(f"services.{name}")
    
    # Generyczne przekształcanie konfiguracji na parametry CLI:
    # {"model_name": "qwen"} -> --model-name qwen
    for key, value in config_data.items():
        if value is not None and not isinstance(value, (dict, list)):
            cli_flag = f"--{key.replace('_', '-')}"
            cmd.extend([cli_flag, str(value)])

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
    env["SERVICE_CONFIG"] = json.dumps(config_data)

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
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            kill_process_tree(proc.pid)
            
        del _active_processes[name]
        _service_configs.pop(name, None)
    return True

def stop_all_services() -> None:
    for name in list(_active_processes.keys()):
        _stop_service(name)

def get_all_services_status() -> dict:
    status = {}
    for name, proc in list(_active_processes.items()):
        status[name] = "running" if proc.poll() is None else "stopped"
    return status
    
def get_active_services_registration() -> dict:
    reg = {}
    for name, proc in list(_active_processes.items()):
        if proc.poll() is None:
            reg[name] = _service_configs.get(name, {})
    return reg
