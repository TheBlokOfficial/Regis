import asyncio
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from shared import ConfigStore, get_service_root, get_logger, sanitize_identifier

from server.ai.tts.factory import TTSFactory
from server.ai.tts.models import ActiveTTSBackendConfig, TTSInstanceConfig, TTSInstanceFileContent, TTSProviderType
from server.voice.tts import BaseTTSProvider

logger = get_logger("regis.ai.tts.registry")

_DEFAULT_INSTANCE_ID = "tts_elevenlabs_default"


class TTSRegistry:
    """Menedżer instancji backendów TTS przechowywanych w plikach JSON w data/ —
    mirror `ai.llm.registry.BackendRegistry`."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data")).resolve()
        self.backends_dir = self.base_data_dir / "tts_backends"
        self.active_config_path = self.base_data_dir / "active_tts_backend.json"

        self.active_store = ConfigStore(ActiveTTSBackendConfig, self.active_config_path)
        self._lock = asyncio.Lock()
        self._defaults_ensured = False

    async def _ensure_default_instances(self) -> None:
        """Tworzy domyślną instancję TTS jeśli folder jest pusty. Wykonuje się tylko raz.

        Best-effort migracja: jeśli istnieje legacy `data/voice/config.json`
        (`VoiceProvidersConfig`, sprzed wprowadzenia rejestru wielu instancji),
        klucz/voice_id/model ElevenLabs są przenoszone do nowej instancji zamiast
        zgubione. Brak legacy pliku -> pusta domyślna instancja."""
        if self._defaults_ensured:
            return

        async with self._lock:
            if self._defaults_ensured:
                return

            self.backends_dir.mkdir(parents=True, exist_ok=True)
            existing_files = list(self.backends_dir.glob("*.json"))

            if not existing_files:
                logger.info("Brak zadeklarowanych instancji TTS. Tworzenie instancji domyślnej...")

                options: dict[str, Any] = {
                    "api_key": "",
                    "voice_id": "pNInz6obpgDQGcFmaJgB",
                    "model_id": "eleven_multilingual_v2",
                }
                legacy_path = self.base_data_dir / "voice" / "config.json"
                if legacy_path.exists():
                    from server.voice.config import VoiceProvidersConfig

                    legacy = await asyncio.to_thread(ConfigStore(VoiceProvidersConfig, legacy_path).load)
                    if legacy.elevenlabs_api_key:
                        logger.info("Migracja klucza ElevenLabs z legacy data/voice/config.json do rejestru TTS.")
                    options = {
                        "api_key": legacy.elevenlabs_api_key,
                        "voice_id": legacy.elevenlabs_voice_id,
                        "model_id": legacy.elevenlabs_model_id,
                    }

                content = TTSInstanceFileContent(
                    type=TTSProviderType.ELEVENLABS,
                    name="ElevenLabs",
                    options=options,
                )
                await asyncio.to_thread(
                    ConfigStore(TTSInstanceFileContent, self.backends_dir / f"{_DEFAULT_INSTANCE_ID}.json").save,
                    content,
                )
                await asyncio.to_thread(
                    self.active_store.save, ActiveTTSBackendConfig(active_id=_DEFAULT_INSTANCE_ID)
                )

            self._defaults_ensured = True

    async def create_instance(
        self,
        provider_type: TTSProviderType,
        name: str,
        options: Dict[str, Any],
        custom_id: Optional[str] = None,
    ) -> TTSInstanceConfig:
        await self._ensure_default_instances()
        instance_id = custom_id or f"tts_{uuid.uuid4().hex[:8]}"
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        content = TTSInstanceFileContent(type=provider_type, name=name, options=options)
        file_path = self.backends_dir / f"{instance_id}.json"

        async with self._lock:
            await asyncio.to_thread(ConfigStore(TTSInstanceFileContent, file_path).save, content)

        logger.info(f"Utworzono nową instancję TTS [{name}] z ID: {instance_id}")
        return TTSInstanceConfig(id=instance_id, **content.model_dump())

    async def update_instance(self, backend_id: str, options: Dict[str, Any]) -> TTSInstanceConfig:
        """Nadpisuje `options` istniejącej instancji (typ/nazwa zostają) — używane przez
        shim kompatybilności `PUT /api/v1/voice/providers/config` (`voice/provider_routes.py`)."""
        await self._ensure_default_instances()
        sanitize_identifier(backend_id, field_name="backend_id")
        file_path = self.backends_dir / f"{backend_id}.json"

        async with self._lock:
            if not file_path.exists():
                raise ValueError(f"Instancja TTS [{backend_id}] nie istnieje.")
            existing = await asyncio.to_thread(ConfigStore(TTSInstanceFileContent, file_path).load)
            updated = existing.model_copy(update={"options": options})
            await asyncio.to_thread(ConfigStore(TTSInstanceFileContent, file_path).save, updated)

        return TTSInstanceConfig(id=backend_id, **updated.model_dump())

    async def load_all_instances(self) -> Dict[str, TTSInstanceConfig]:
        await self._ensure_default_instances()
        instances: Dict[str, TTSInstanceConfig] = {}

        async with self._lock:
            for file_path in self.backends_dir.glob("*.json"):
                try:
                    instance_id = file_path.stem
                    content = await asyncio.to_thread(ConfigStore(TTSInstanceFileContent, file_path).load)
                    instances[instance_id] = TTSInstanceConfig(id=instance_id, **content.model_dump())
                except Exception as e:
                    logger.error(f"Błąd podczas wczytywania pliku instancji TTS [{file_path}]: {e}")

        return instances

    async def get_active_backend_id(self) -> str:
        await self._ensure_default_instances()
        async with self._lock:
            cfg = await asyncio.to_thread(
                self.active_store.load, default_factory=lambda: ActiveTTSBackendConfig(active_id=_DEFAULT_INSTANCE_ID)
            )
            return cfg.active_id

    async def set_active_backend_id(self, backend_id: str) -> None:
        sanitize_identifier(backend_id, field_name="backend_id")
        async with self._lock:
            await asyncio.to_thread(self.active_store.save, ActiveTTSBackendConfig(active_id=backend_id))
        logger.info(f"Zmieniono aktywną instancję TTS na: [{backend_id}]")

    async def delete_instance(self, backend_id: str) -> bool:
        sanitize_identifier(backend_id, field_name="backend_id")
        await self._ensure_default_instances()
        async with self._lock:
            active_cfg = await asyncio.to_thread(
                self.active_store.load, default_factory=lambda: ActiveTTSBackendConfig(active_id=_DEFAULT_INSTANCE_ID)
            )
            if backend_id == active_cfg.active_id:
                raise ValueError(
                    f"Nie można usunąć aktywnej instancji TTS [{backend_id}]. Najpierw przełącz na inną."
                )

            file_path = self.backends_dir / f"{backend_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Usunięto instancję TTS [{backend_id}] z dysku.")
                return True
            return False

    async def get_active_provider(self) -> BaseTTSProvider:
        all_instances = await self.load_all_instances()

        if not all_instances:
            raise RuntimeError("Brak jakichkolwiek zadeklarowanych instancji TTS w folderze data/tts_backends/")

        active_id = await self.get_active_backend_id()

        if active_id in all_instances:
            selected_config = all_instances[active_id]
        else:
            first_id = next(iter(all_instances.keys()))
            logger.warning(
                f"⚠️ Wskazane aktywne ID TTS [{active_id}] nie istnieje na dysku. "
                f"Bezpieczne przełączenie na pierwszą dostępną instancję: [{first_id}]"
            )
            selected_config = all_instances[first_id]
            await self.set_active_backend_id(first_id)

        return TTSFactory.create_provider(selected_config)
