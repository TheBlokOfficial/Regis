"""
Moduł komunikacji z Kontrolerem: Auto-Discovery i pętla heartbeat.
"""
import asyncio
import logging
import requests

from client import config
from client.services.llm.service import llm_service


class RegistrationManager:
    """Odpowiada wyłącznie za zgłaszanie obecności usługi LLM w Kontrolerze."""

    def __init__(self):
        self.reg_task: asyncio.Task | None = None

    def resolve_controller(self):
        if llm_service.controller_url_setting == "auto":
            from protocol.discovery import discover_controller
            try:
                llm_service.controller_url = discover_controller()
            except Exception as e:
                logging.warning(f"Auto-Discovery zawiodło: {e}. Używam localhost.")
                llm_service.controller_url = "http://127.0.0.1:8000"
        else:
            llm_service.controller_url = llm_service.controller_url_setting

    def get_registration_payload(self) -> dict:
        from protocol.discovery import get_local_ip
        settings = config.load_settings()
        host = settings.get("worker_host", get_local_ip())
        reg_host = get_local_ip() if host == "0.0.0.0" else host

        return {
            "id": llm_service.node_id,
            "name": llm_service.node_id,
            "host": reg_host,
            "port": llm_service.port,
            "services": {
                "llm": {
                    "model_name": llm_service.selected_model,
                    "priority": llm_service.priority,
                    "mode": "extended",
                    "port": llm_service.port
                }
            }
        }

    async def start_registration(self):
        self.resolve_controller()
        payload = self.get_registration_payload()

        try:
            resp = requests.post(f"{llm_service.controller_url}/v1/nodes/register", json=payload, timeout=5)
            if resp.ok:
                logging.info(f"Usługa LLM '{llm_service.node_id}' zarejestrowana w Kontrolerze ({llm_service.controller_url}).")
        except requests.RequestException as e:
            logging.warning(f"Brak pierwszej rejestracji w Kontrolerze: {e}.")

        async def _loop():
            failures = 0
            while True:
                await asyncio.sleep(15)
                try:
                    resp = await asyncio.to_thread(requests.post, f"{llm_service.controller_url}/v1/nodes/register", json=payload, timeout=5)
                    if resp.ok:
                        failures = 0
                    else:
                        failures += 1
                except Exception:
                    failures += 1

                if failures >= 2 and llm_service.controller_url_setting == "auto":
                    await asyncio.to_thread(self.resolve_controller)

        self.reg_task = asyncio.create_task(_loop())

    def stop_registration(self):
        if self.reg_task:
            self.reg_task.cancel()
            self.reg_task = None


registration_manager = RegistrationManager()
