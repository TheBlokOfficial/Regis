from enum import Enum

class SatelliteState(str, Enum):
    """Oficjalne stany maszyny stanów usługi Satelity."""
    INITIALIZING = "INITIALIZING"
    WAITING = "WAITING"
    WAKEWORD = "WAKEWORD"
    LISTENING = "LISTENING"
    STREAMING = "STREAMING"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
