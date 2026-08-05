import queue as _q
import threading

class EventBus:
    """Odpowiada za komunikację z UI (Monitorem) przez eventy.

    Wysyła zdarzenia bezpośrednio przez otwarty WebSocket do Kontrolera
    używając globalnego `bus_publish`.
    """

    def __init__(self, satellite_id: str | None = None):
        self.satellite_id = satellite_id
        self.queue = _q.Queue()
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)
        self.worker_thread.start()
        
    def _worker(self):
        from client.controller_api import bus_publish
        while True:
            event = self.queue.get()
            try:
                if self.satellite_id:
                    event["satellite_id"] = self.satellite_id
                bus_publish(event)
            except Exception:
                pass
            self.queue.task_done()
                
    def emit(self, event: dict):
        try:
            self.queue.put_nowait(event)
        except Exception:
            pass
            
    def log(self, message: str):
        """Pomocnik rzucający logi w Monitor Audio, wyłapywane jako info."""
        print(message, flush=True)
        self.emit({"type": "info", "message": message})
