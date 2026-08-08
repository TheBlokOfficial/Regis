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
from client.services.ollama_worker.engine import LLMEngine
from protocol.schemas import OllamaWorkerConfig, ServiceState
from client.services.base import BaseService
from client.services.ollama_worker.ollama_client import preload_model, unload_model, is_available

logging.basicConfig(level=logging.INFO, format="%(message)s")


class OllamaWorkerService(BaseService):
    """Bezportowa usługa Ollama Worker wykonywana jako podproces Sidecar."""

    def __init__(self, config_obj: OllamaWorkerConfig | None = None):
        super().__init__(service_name="ollama_worker", config_class=OllamaWorkerConfig, config_obj=config_obj)
        settings = config.load_settings()

        self.selected_model = self.config.model_name or settings.get("selected_model", "qwen3.5:9b")
        self.llm_engine: LLMEngine | None = None
        self._ensure_ready_task: asyncio.Task | None = None

    async def _ensure_ready_loop(self):
        """Pętla samolecząca. Działa cyklicznie w tle, gdy worker jest w stanie INITIALIZING."""
        settings = config.load_settings()
        ollama_url = settings.get('ollama_url', 'http://127.0.0.1:11434')
        
        while self.state == ServiceState.INITIALIZING:
            try:
                if await is_available(ollama_url):
                    logging.info(f"[Ollama Worker] Ollama dostępna. Próba załadowania modelu {self.selected_model}...")
                    success = await preload_model(ollama_url, self.selected_model)
                    if success:
                        await self._set_state(ServiceState.READY)
                        logging.info("[Ollama Worker] Model w VRAM. Usługa gotowa (READY).")
                        break
                    else:
                        logging.warning("[Ollama Worker] Nie udało się wgrać modelu. Kolejna próba za 3s...")
                else:
                    logging.debug("[Ollama Worker] Ollama offline. Wyczekiwanie...")
            except Exception as e:
                logging.error(f"[Ollama Worker] Błąd w pętli inicjalizacyjnej: {e}")
                
            await asyncio.sleep(3.0)

    def _trigger_healing(self):
        """Anuluje obecną pętlę (jeśli jest) i uruchamia nową, przechodząc do INITIALIZING."""
        if self._ensure_ready_task and not self._ensure_ready_task.done():
            self._ensure_ready_task.cancel()
        self.state = ServiceState.INITIALIZING
        self._ensure_ready_task = asyncio.create_task(self._ensure_ready_loop())

    async def start(self):
        self.llm_engine = LLMEngine(model_name=self.selected_model, temperature=0.1)
        self._trigger_healing()
        await super().start()

    async def stop(self):
        if self._ensure_ready_task:
            self._ensure_ready_task.cancel()
        if self.llm_engine:
            settings = config.load_settings()
            ollama_url = settings.get('ollama_url', 'http://127.0.0.1:11434')
            await unload_model(ollama_url, self.selected_model)

    async def handle_command(self, command_type: str, payload: dict, task_id: str | None):
        from protocol.schemas import ServiceCommand
        if command_type in (ServiceCommand.CHAT_STREAM, ServiceCommand.CHAT_STREAM.value):
            if self.state != ServiceState.READY:
                logging.warning(f"Odrzucono zadanie - worker jest {self.state.value}")
                await self.send_task_event(task_id, {"type": "error", "content": f"Ollama worker is currently {self.state.value}"})
                return
            await self._process_chat_stream(payload, task_id)

    async def _process_chat_stream(self, payload: dict, task_id: str | None):
        requested_model = payload.get("model")
        
        # Dynamic Model Swapping (jeśli poproszono o inny model niż mamy)
        if requested_model and requested_model != self.selected_model:
            logging.info(f"Otrzymano żądanie zmiany modelu z {self.selected_model} na {requested_model}")
            settings = config.load_settings()
            ollama_url = settings.get('ollama_url', 'http://127.0.0.1:11434')
            await unload_model(ollama_url, self.selected_model)
            
            self.selected_model = requested_model
            self.llm_engine = LLMEngine(model_name=self.selected_model, temperature=0.1)
            
            # Wracamy do INITIALIZING i uruchamiamy pętlę od nowa, by wgrać nowy model
            self._trigger_healing()
            await self.send_task_event(task_id, {"type": "error", "content": f"Changing model to {requested_model}. Please retry in a few seconds."})
            return

        await self._set_state(ServiceState.BUSY)
        
        messages = payload.get("messages", [])
        tools = payload.get("tools")
        response_text = ""

        try:
            async for event in self.llm_engine.generate_response_stream(
                messages=messages,
                tools=tools
            ):
                if event["type"] == "content":
                    response_text += event["content"]
                if event["type"] == "done":
                    response_text = event["content"]
                    
                await self.send_task_event(task_id, event)
                
            await self._set_state(ServiceState.READY)

        except Exception as e:
            logging.exception("Błąd generacji odpowiedzi Ollama Worker")
            await self.send_task_event(task_id, {"type": "error", "content": f"Generation failed: {str(e)}"})
            
            # Samoleczenie po awarii sieci w trackie generacji
            self._trigger_healing()


def main():
    service = OllamaWorkerService()
    try:
        asyncio.run(service.start())
    except KeyboardInterrupt:
        asyncio.run(service.stop())


if __name__ == "__main__":
    main()
