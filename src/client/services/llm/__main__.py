"""
Główny orkiestrator usługi LLM Worker (Bezportowy Sidecar Worker).

Usługa nie otwiera własnych portów HTTP. Podłącza się do magistrali Aplikacji Klienckiej
(internal_proxy.py) i pasywnie wykonuje komendy wnioskowania LLM.
"""
import os
import sys
import asyncio
import logging
from client import config
from client.engines.llm_engine import LLMEngine
from client.services.remote_tools_registry import RemoteToolsRegistry
from protocol.schemas import LLMConfig
from client.services.base import BaseService
logging.basicConfig(level=logging.INFO, format="%(message)s")


class LLMService(BaseService):
    """Bezportowa usługa LLM wykonywana jako podproces Sidecar."""

    def __init__(self, config_obj: LLMConfig | None = None):
        super().__init__(service_name="llm", config_class=LLMConfig, config_obj=config_obj)
        settings = config.load_settings()

        self.selected_model = self.config.model_name or settings.get("selected_model", "qwen3.5:9b")
        self.llm_engine: LLMEngine | None = None

    async def start(self):
        self.llm_engine = LLMEngine(model_name=self.selected_model, temperature=0.1)
        try:
            await self.llm_engine.preload_model()
            logging.info(f"Usługa LLM załadowana w pamięci VRAM ({self.selected_model}). Czekam na komendy z magistrali...")
        except Exception as e:
            logging.error(f"Błąd ładowania modelu LLM: {e}")
            sys.exit(1)

        await super().start()

    async def stop(self):
        if self.llm_engine:
            await self.llm_engine.unload_model()

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
                await self.send_task_event(task_id, event)

            await self.send_task_event(task_id, {"type": "done", "content": response_text})
        except Exception as e:
            logging.exception("Błąd generacji odpowiedzi LLM w podprocesie")
            await self.send_task_event(task_id, {"type": "error", "content": str(e)})


def main():
    service = LLMService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        asyncio.run(service.stop())


if __name__ == "__main__":
    main()
