import sys
import os
import subprocess
import psutil

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
