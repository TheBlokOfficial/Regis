"""
Moduł zarządzania stanem i silnikiem usługi LLM (LLMService).
"""
import os
import logging
import socket

from client import config
from client.engines.llm_engine import LLMEngine
from protocol.schemas import LLMConfig


class LLMService:
    """Odpowiada za konfigurację, stan oraz ładowanie/uwalnianie VRAM dla silnika LLM."""

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
        self.port = config_obj.port or settings.get("llm_port", 8001)
        self.priority = getattr(config_obj, "priority", 100)
        self.controller_url_setting = config_obj.controller_url or settings.get("controller_url", "http://127.0.0.1:8000")
        self.node_id = settings.get("worker_id", settings.get("instance_name", f"llm-{socket.gethostname()}"))

        self.llm_engine: LLMEngine | None = None
        self.controller_url: str = ""

    async def start_engine(self):
        """Ładuje model LLM do pamięci VRAM."""
        self.llm_engine = LLMEngine(model_name=self.selected_model, temperature=0.1)
        try:
            await self.llm_engine.preload_model()
            logging.info(f"Silnik LLM ({self.selected_model}) załadowany do VRAM.")
        except Exception as e:
            logging.error(f"Nie można uruchomić usługi LLM - model niedostępny: {e}")
            raise e

    async def stop_engine(self):
        """Wyładowuje model z pamięci VRAM."""
        if self.llm_engine:
            await self.llm_engine.unload_model()
            logging.info("Silnik LLM wyładowany z VRAM.")


# Globalna instancja usługi LLM
llm_service = LLMService()
