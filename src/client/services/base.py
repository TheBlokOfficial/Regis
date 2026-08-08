import os
import json
import asyncio
import logging
import httpx
import sys
from pydantic import BaseModel
from typing import Type
from protocol.schemas import ServiceState

class BaseService:
    """Współdzielona klasa bazowa dla bezportowych usług pracujących jako Sidecar."""

    def __init__(self, service_name: str, config_class: Type[BaseModel], config_obj: BaseModel | None = None):
        self.service_name = service_name
        
        if config_obj is None:
            raw_config = os.environ.get("SERVICE_CONFIG")
            if raw_config:
                config_obj = config_class.model_validate_json(raw_config)
            else:
                config_obj = config_class()
                
        self.config = config_obj
        self.internal_proxy_url = getattr(self.config, "internal_proxy_url", "http://127.0.0.1:47831")
        self.state: ServiceState = ServiceState.INITIALIZING

    async def _set_state(self, new_state: ServiceState):
        """Zmiana stanu operacyjnego usługi i zaraportowanie w konsoli."""
        if self.state != new_state:
            logging.info(f"[{self.service_name}] Zmiana stanu operacyjnego: {self.state.value} -> {new_state.value}")
            self.state = new_state

    async def stop(self):
        """Metoda czyszcząca wywoływana przy zamykaniu usługi. Do nadpisania w klasach potomnych."""
        pass

    async def start(self):
        """Metoda inicjalizująca usługę. Do opcjonalnego nadpisania, z wywołaniem super().start() lub listen_for_commands()."""
        await self.listen_for_commands()

    async def listen_for_commands(self):
        """Nasłuchuje komend z magistrali proxy (SSE), filtrując po polu `service`."""
        url = f"{self.internal_proxy_url}/internal/service_commands"
        while True:
            try:
                async with httpx.AsyncClient(timeout=None) as client:
                    async with client.stream("GET", url) as response:
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            data_str = line[6:].strip()
                            if not data_str:
                                continue
                            try:
                                cmd_event = json.loads(data_str)
                                target_service = cmd_event.get("service")
                                if target_service and target_service != self.service_name:
                                    continue
                                command_type = cmd_event.get("command")
                                
                                # Graceful shutdown na polecenie magistrali
                                from client.ipc_schemas import SystemCommand
                                if command_type in (SystemCommand.STOP, SystemCommand.SHUTDOWN, SystemCommand.STOP.value, SystemCommand.SHUTDOWN.value):
                                    logging.info(f"[{self.service_name}] Otrzymano sygnał zamknięcia ({command_type}). Rozpoczynam wyczyszczenie zasobów...")
                                    try:
                                        await self.stop()
                                    except Exception as e:
                                        logging.error(f"[{self.service_name}] Błąd podczas zatrzymywania: {e}")
                                    sys.exit(0)
                                    
                                payload = cmd_event.get("payload")
                                if payload is None:
                                    payload = {k: v for k, v in cmd_event.items() if k not in ("command", "service", "task_id")}
                                
                                task_id = cmd_event.get("task_id")
                                asyncio.create_task(self.handle_command(command_type, payload, task_id))
                            except Exception as e:
                                logging.error(f"Błąd dekodowania komendy dla usługi {self.service_name}: {e}")
            except Exception as e:
                logging.warning(f"Utracono połączenie z magistralą Klienta. Ponawiam za 3s... ({e})")
                await asyncio.sleep(3)

    async def handle_command(self, command_type: str, payload: dict, task_id: str | None):
        """Abstrakcyjna metoda do zaimplementowania w klasach pochodnych. Wywoływana przy odebraniu pasującej komendy."""
        pass

    async def send_task_event(self, task_id: str | None, event: dict):
        """Odsyłanie zdarzenia przez internal proxy."""
        if not task_id:
            return
        url = f"{self.internal_proxy_url}/internal/task_event"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={"task_id": task_id, "event": event})
        except Exception as e:
            logging.warning(f"Błąd wysyłania ramek {self.service_name} do proxy: {e}")
