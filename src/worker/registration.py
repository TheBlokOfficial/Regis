import asyncio
import logging
import socket

import requests


class WorkerRegistrationManager:
    """Odpowiada za Auto-Discovery oraz rejestrację Węzła Roboczego w Kontrolerze (w tym loop Heartbeat)."""

    def __init__(self):
        self.worker_id: str = ""
        self.controller_url: str = ""
        self.registration_payload: dict = {}
        self._task: asyncio.Task | None = None

    def resolve_controller_url(self, settings: dict) -> str:
        url = settings.get("controller_url", "http://127.0.0.1:8000")
        if url == "auto":
            from protocol.discovery import discover_controller
            try:
                return discover_controller()
            except Exception as e:
                logging.warning(f"Auto-Discovery zawiodło, używam fallbacku (http://127.0.0.1:8000). Błąd: {e}")
                return "http://127.0.0.1:8000"
        return url

    def register(self, settings: dict, selected_model: str, priority: int = 100):
        self.worker_id = settings.get("worker_id", f"worker-{socket.gethostname()}")
        self.controller_url = self.resolve_controller_url(settings)

        from protocol.discovery import get_local_ip

        worker_port = settings.get("worker_port", 8001)
        worker_host = settings.get("worker_host", get_local_ip())
        registration_host = get_local_ip() if worker_host in ("0.0.0.0", "127.0.0.1", "localhost") else worker_host

        self.registration_payload = {
            "id": self.worker_id,
            "host": registration_host,
            "port": worker_port,
            "model_name": selected_model,
            "priority": priority
        }

        try:
            resp = requests.post(f"{self.controller_url}/v1/workers/register", json=self.registration_payload, timeout=5)
            if resp.ok:
                logging.info(f"Węzeł '{self.worker_id}' zarejestrowany w Kontrolerze ({self.controller_url}).")
            else:
                logging.warning(f"Rejestracja w Kontrolerze zwróciła status {resp.status_code}.")
        except requests.RequestException as e:
            logging.warning(f"Nie udało się zarejestrować w Kontrolerze przy starcie: {e}")

    async def start_heartbeat(self):
        """Uruchamia pętlę odnawiania rejestracji co 15 sekund w tle."""
        async def _loop():
            while True:
                await asyncio.sleep(15)
                try:
                    await asyncio.to_thread(
                        requests.post,
                        f"{self.controller_url}/v1/workers/register",
                        json=self.registration_payload,
                        timeout=5
                    )
                except Exception:
                    pass

        self._task = asyncio.create_task(_loop())

    def unregister(self):
        """Zatrzymuje pętlę i wyrejestrowuje Węzeł Roboczy z Kontrolera."""
        if self._task:
            self._task.cancel()
        try:
            requests.delete(f"{self.controller_url}/v1/workers/{self.worker_id}", timeout=5)
            logging.info(f"Węzeł '{self.worker_id}' wyrejestrowany z Kontrolera.")
        except requests.RequestException as e:
            logging.warning(f"Nie udało się wyrejestrować z Kontrolera: {e}")


registration_manager = WorkerRegistrationManager()
