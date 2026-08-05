from enum import Enum

class OllamaWorkerState(str, Enum):
    """
    Klarowne, wysokopoziomowe stany dla usługi Ollama Worker.
    Kontroler na ich podstawie wie, czy może do nas wysłać zapytanie.
    """
    INITIALIZING = "INITIALIZING" # Usługa niedostępna (uruchamia się, pinguje Ollamę, pobiera/ładuje model, wraca po awarii)
    READY = "READY"               # Gotowa na zapytania
    BUSY = "BUSY"                 # Zajęta generowaniem strumienia
