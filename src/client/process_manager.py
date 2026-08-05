import os
import sys
import subprocess
import json
import logging
import time
import threading
from client.proc_utils import cleanup_orphaned_processes, get_executable_command, kill_process_tree, assign_to_job_object
from client.config import DATA_DIR

from enum import Enum

logger = logging.getLogger(__name__)

class ProcessAction(str, Enum):
    """Oficjalny spis dopuszczalnych akcji na podprocesach usług."""
    START = "start"
    STOP = "stop"
    RESTART = "restart"

class ProcessStatus(str, Enum):
    """Oficjalny spis stanów wykonawczych podprocesów usług."""
    RUNNING = "running"
    STOPPED = "stopped"

_active_processes: dict[str, subprocess.Popen] = {}
_service_configs: dict[str, dict] = {}
_process_lock = threading.Lock()

def control_service(name: str, action: str | ProcessAction, config_data: dict = None) -> bool:
    """Zarządza lokalnym stanem podprocesów usługi w systemie (start, stop, restart)."""
    with _process_lock:
        act = action.value.lower() if isinstance(action, ProcessAction) else str(action).lower()
        if act == ProcessAction.START:
            return _start_service(name, config_data)
        elif act == ProcessAction.STOP:
            return _stop_service(name)
        elif act == ProcessAction.RESTART:
            _stop_service(name)
            return _start_service(name, config_data)
        return False

DISPLAY_NAMES = {
    "satellite": "Satelita",
    "audio": "Audio (STT+TTS)",
    "llm": "LLM (Agent)",
}

def _stream_service_logs(name: str, proc: subprocess.Popen, log_path: str):
    tag = DISPLAY_NAMES.get(name, name.capitalize())
    with open(log_path, "a", encoding="utf-8") as f:
        for line in iter(proc.stdout.readline, b''):
            text = line.decode('utf-8', errors='replace').rstrip()
            if text:
                f.write(text + '\n')
                f.flush()
                logger.info(f"[{tag}] {text}")

def _start_service(name: str, config_data: dict = None) -> bool:
    tag = DISPLAY_NAMES.get(name, name.capitalize())
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

    os.makedirs(os.path.join(DATA_DIR, "logs"), exist_ok=True)
    log_path = os.path.join(DATA_DIR, "logs", f"{name}.log")

    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }

    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["SERVICE_CONFIG"] = json.dumps(config_data)

    try:
        proc = subprocess.Popen(cmd, env=env, **kwargs)
        assign_to_job_object(proc)
        _active_processes[name] = proc

        t = threading.Thread(target=_stream_service_logs, args=(name, proc, log_path), daemon=True)
        t.start()

        logger.info(f"[{tag}] Usługa została włączona.")
        return True
    except Exception as e:
        logger.error(f"[{tag}] Błąd uruchamiania usługi: {e}")
        return False

def _stop_service(name: str) -> bool:
    tag = DISPLAY_NAMES.get(name, name.capitalize())
    if name in _active_processes:
        proc = _active_processes[name]
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            kill_process_tree(proc.pid)
            
        del _active_processes[name]
        _service_configs.pop(name, None)
        logger.info(f"[{tag}] Usługa została wyłączona.")
    return True
    return True

def stop_all_services() -> None:
    for name in list(_active_processes.keys()):
        _stop_service(name)

def get_all_services_status() -> dict[str, ProcessStatus]:
    status = {}
    for name, proc in list(_active_processes.items()):
        status[name] = ProcessStatus.RUNNING if proc.poll() is None else ProcessStatus.STOPPED
    return status
    
def get_active_services_registration() -> dict:
    reg = {}
    for name, proc in list(_active_processes.items()):
        if proc.poll() is None:
            reg[name] = _service_configs.get(name, {})
    return reg
