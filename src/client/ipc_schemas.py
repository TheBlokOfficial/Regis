from enum import Enum

class SystemCommand(str, Enum):
    """Lokalne komendy cyklu życia (infrastrukturalne) zarządzane przez ProcessManager i Klienta."""
    STOP = "stop"
    SHUTDOWN = "shutdown"
