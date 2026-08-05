"""
Główny orkiestrator usługi LLM Worker (Bezportowy Sidecar Worker).

Usługa nie otwiera własnych portów HTTP. Podłącza się do magistrali Aplikacji Klienckiej
(internal_proxy.py) i pasywnie wykonuje komendy wnioskowania LLM.
"""
import os
import sys
import asyncio
import json
import logging
from client import config
from client.engines.llm_engine import LLMEngine
from client.services.remote_tools_registry import RemoteToolsRegistry
from protocol.schemas import LLMConfig
logging.basicConfig(level=logging.INFO, format="%(message)s")


class LLMService:
    """Bezportowa usługa LLM wykonywana jako podproces Sidecar."""

    def __init__(self, config_obj: LLMConfig | None = None):
        if config_obj is None:
            raw_config = os.environ.get("SERVICE_CONFIG")
            if raw_config:
                config_obj = LLMConfig.model_validate_json(raw_config)
            else:
                config_obj = LLMConfig()

        self.config = config_obj
        settings = config.load_settings()

        self.selected_model = config_obj.model_name or settings.get("selected_model", "qwen3.5:9b")
        self.internal_proxy_url = getattr(config_obj, "internal_proxy_url", "http://127.0.0.1:47831")
        self.llm_engine: LLMEngine | None = None

    async def start(self):
        self.llm_engine = LLMEngine(model_name=self.selected_model, temperature=0.1)
        try:
            await self.llm_engine.preload_model()
            logging.info(f"Usługa LLM załadowana w pamięci VRAM ({self.selected_model}). Czekam na komendy z magistrali...")
        except Exception as e:
            logging.error(f"Błąd ładowania modelu LLM: {e}")
            sys.exit(1)

        await self._listen_for_commands()

    async def stop(self):
        if self.llm_engine:
            await self.llm_engine.unload_model()

    async def _listen_for_commands(self):
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
                                if target_service != "llm":
                                    continue
                                command_type = cmd_event.get("command")
                                payload = cmd_event.get("payload", {})
                                task_id = cmd_event.get("task_id")
                                asyncio.create_task(self.handle_command(command_type, payload, task_id))
                            except Exception as e:
                                logging.error(f"Błąd dekodowania komendy LLM: {e}")
            except Exception as e:
                logging.warning(f"Utracono połączenie z magistralą Klienta. Ponawiam za 3s... ({e})")
                await asyncio.sleep(3)

    async def handle_command(self, command_type: str, payload: dict, task_id: str | None):
        if command_type == "chat_stream":
            await self._process_chat_stream(payload, task_id)

    async def _process_chat_stream(self, payload: dict, task_id: str | None):
        message = payload.get("message", "")
        system_prompt = payload.get("system_prompt", "")
        history = payload.get("history", [])
        controller_url = payload.get("controller_url", "http://127.0.0.1:8000")
        room = payload.get("room")

        remote_tools = RemoteToolsRegistry(controller_url, room=room)
        response_text = ""

        try:
            async for event in self.llm_engine.generate_response_stream(
                system_prompt=system_prompt,
                history=history,
                current_message=message,
                tools_registry=remote_tools
            ):
                if event["type"] == "content":
                    response_text += event["content"]
                if event["type"] == "done":
                    response_text = event["content"]

                # Odsyłanie zdarzenia przez internal_proxy do Kontrolera
                await self._send_task_event(task_id, event)

            await self._send_task_event(task_id, {"type": "done", "content": response_text})
        except Exception as e:
            logging.exception("Błąd generacji odpowiedzi LLM w podprocesie")
            await self._send_task_event(task_id, {"type": "error", "content": str(e)})

    async def _send_task_event(self, task_id: str | None, event: dict):
        if not task_id:
            return
        url = f"{self.internal_proxy_url}/internal/task_event"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(url, json={"task_id": task_id, "event": event})
        except Exception as e:
            logging.warning(f"Błąd wysyłania ramek LLM do proxy: {e}")


def main():
    service = LLMService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        asyncio.run(service.stop())


if __name__ == "__main__":
    main()
