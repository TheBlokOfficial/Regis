"""Rejestr instancji backendów TTS — mirror `ai/llm/registry.py`, cała mechanika
w `ai/provider_registry.py`."""

import asyncio
from pathlib import Path
from typing import Any, Optional

from shared import ConfigStore, get_logger
from shared import data_dir as shared_data_dir

from server.ai.legacy_config import VoiceProvidersConfig
from server.ai.provider_registry import ProviderRegistry
from server.ai.tts.factory import TTSFactory
from server.ai.tts.models import TTSInstanceConfig, TTSInstanceFileContent, TTSProviderType
from server.ports.tts import BaseTTSProvider

logger = get_logger("regis.ai.tts.registry")

_DEFAULT_INSTANCE_ID = "tts_elevenlabs_default"


class TTSRegistry(ProviderRegistry[TTSInstanceFileContent, TTSInstanceConfig, BaseTTSProvider]):
    """Menedżer instancji backendów TTS przechowywanych w plikach JSON w `data/tts_backends/`."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        super().__init__(
            base_data_dir=data_dir or shared_data_dir(__file__),
            instances_dir_name="tts_backends",
            active_file_name="active_tts_backend.json",
            content_cls=TTSInstanceFileContent,
            instance_cls=TTSInstanceConfig,
            id_prefix="tts",
            default_instance_id=_DEFAULT_INSTANCE_ID,
            label="instancji TTS",
        )

    async def _seed_default_instances(self) -> None:
        """Jedna pusta instancja ElevenLabs (mirror seedu STT).

        Best-effort migracja z legacy `data/voice/config.json` (patrz
        `ai/legacy_config.py`) — klucz, `voice_id` i `model_id` przenoszą się
        do nowej instancji zamiast zginąć."""
        options: dict[str, Any] = {
            "api_key": "",
            "voice_id": "pNInz6obpgDQGcFmaJgB",
            "model_id": "eleven_multilingual_v2",
        }
        legacy_path = self.base_data_dir / "voice" / "config.json"
        if legacy_path.exists():
            legacy = await asyncio.to_thread(ConfigStore(VoiceProvidersConfig, legacy_path).load)
            if legacy.elevenlabs_api_key:
                logger.info("Migracja klucza ElevenLabs z legacy data/voice/config.json do rejestru TTS.")
            options = {
                "api_key": legacy.elevenlabs_api_key,
                "voice_id": legacy.elevenlabs_voice_id,
                "model_id": legacy.elevenlabs_model_id,
            }

        await self._write_seed(
            _DEFAULT_INSTANCE_ID,
            TTSInstanceFileContent(type=TTSProviderType.ELEVENLABS, name="ElevenLabs", options=options),
            set_active=True,
        )

    def _create_provider(self, config: TTSInstanceConfig) -> BaseTTSProvider:
        return TTSFactory.create_provider(config)
