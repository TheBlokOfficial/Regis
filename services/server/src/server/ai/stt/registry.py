"""Rejestr instancji backendów STT — mirror `ai/llm/registry.py`, cała mechanika
w `ai/provider_registry.py`."""

import asyncio
from pathlib import Path
from typing import Any, Optional

from shared import ConfigStore, get_logger, get_service_root

from server.ai.legacy_config import VoiceProvidersConfig
from server.ai.provider_registry import ProviderRegistry
from server.ai.stt.factory import STTFactory
from server.ai.stt.models import STTInstanceConfig, STTInstanceFileContent, STTProviderType
from server.ports.stt import BaseSTTProvider

logger = get_logger("regis.ai.stt.registry")

_DEFAULT_INSTANCE_ID = "stt_groq_default"


class STTRegistry(ProviderRegistry[STTInstanceFileContent, STTInstanceConfig, BaseSTTProvider]):
    """Menedżer instancji backendów STT przechowywanych w plikach JSON w `data/stt_backends/`."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        super().__init__(
            base_data_dir=data_dir or (get_service_root(__file__) / "data"),
            instances_dir_name="stt_backends",
            active_file_name="active_stt_backend.json",
            content_cls=STTInstanceFileContent,
            instance_cls=STTInstanceConfig,
            id_prefix="stt",
            default_instance_id=_DEFAULT_INSTANCE_ID,
            label="instancji STT",
        )

    async def _seed_default_instances(self) -> None:
        """Jedna pusta instancja Groq (mirror `bk_openrouter_main` w LLM).

        Best-effort migracja: jeśli istnieje legacy `data/voice/config.json`
        (jednoslotowy config sprzed rejestrów, patrz `ai/legacy_config.py`),
        klucz i model przenoszą się do nowej instancji zamiast zginąć."""
        options: dict[str, Any] = {"api_key": "", "model": "whisper-large-v3-turbo"}
        legacy_path = self.base_data_dir / "voice" / "config.json"
        if legacy_path.exists():
            legacy = await asyncio.to_thread(ConfigStore(VoiceProvidersConfig, legacy_path).load)
            if legacy.groq_api_key:
                logger.info("Migracja klucza Groq z legacy data/voice/config.json do rejestru STT.")
            options = {"api_key": legacy.groq_api_key, "model": legacy.groq_stt_model}

        await self._write_seed(
            _DEFAULT_INSTANCE_ID,
            STTInstanceFileContent(type=STTProviderType.GROQ, name="Groq (Whisper)", options=options),
            set_active=True,
        )

    def _create_provider(self, config: STTInstanceConfig) -> BaseSTTProvider:
        return STTFactory.create_provider(config)
