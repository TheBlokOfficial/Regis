import asyncio
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from shared import ConfigStore, get_service_root, get_logger, sanitize_identifier

from server.ai.stt.factory import STTFactory
from server.ai.stt.models import ActiveSTTBackendConfig, STTInstanceConfig, STTInstanceFileContent, STTProviderType
from server.voice.stt import BaseSTTProvider

logger = get_logger("regis.ai.stt.registry")

_DEFAULT_INSTANCE_ID = "stt_groq_default"


class STTRegistry:
    """Menedżer instancji backendów STT przechowywanych w plikach JSON w data/ —
    mirror `ai.llm.registry.BackendRegistry`."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data")).resolve()
        self.backends_dir = self.base_data_dir / "stt_backends"
        self.active_config_path = self.base_data_dir / "active_stt_backend.json"

        self.active_store = ConfigStore(ActiveSTTBackendConfig, self.active_config_path)
        self._lock = asyncio.Lock()
        self._defaults_ensured = False

    async def _ensure_default_instances(self) -> None:
        """Tworzy domyślną instancję STT jeśli folder jest pusty. Wykonuje się tylko raz.

        Best-effort migracja: jeśli istnieje legacy `data/voice/config.json`
        (`VoiceProvidersConfig`, sprzed wprowadzenia rejestru wielu instancji),
        klucz Groq/model są przenoszone do nowej instancji zamiast zgubione.
        Brak legacy pliku -> pusta domyślna instancja (mirror `bk_openrouter_main`
        w LLM)."""
        if self._defaults_ensured:
            return

        async with self._lock:
            if self._defaults_ensured:
                return

            self.backends_dir.mkdir(parents=True, exist_ok=True)
            existing_files = list(self.backends_dir.glob("*.json"))

            if not existing_files:
                logger.info("Brak zadeklarowanych instancji STT. Tworzenie instancji domyślnej...")

                options: dict[str, Any] = {"api_key": "", "model": "whisper-large-v3-turbo"}
                legacy_path = self.base_data_dir / "voice" / "config.json"
                if legacy_path.exists():
                    from server.voice.config import VoiceProvidersConfig

                    legacy = await asyncio.to_thread(ConfigStore(VoiceProvidersConfig, legacy_path).load)
                    if legacy.groq_api_key:
                        logger.info("Migracja klucza Groq z legacy data/voice/config.json do rejestru STT.")
                    options = {"api_key": legacy.groq_api_key, "model": legacy.groq_stt_model}

                content = STTInstanceFileContent(
                    type=STTProviderType.GROQ,
                    name="Groq (Whisper)",
                    options=options,
                )
                await asyncio.to_thread(
                    ConfigStore(STTInstanceFileContent, self.backends_dir / f"{_DEFAULT_INSTANCE_ID}.json").save,
                    content,
                )
                await asyncio.to_thread(
                    self.active_store.save, ActiveSTTBackendConfig(active_id=_DEFAULT_INSTANCE_ID)
                )

            self._defaults_ensured = True

    async def create_instance(
        self,
        provider_type: STTProviderType,
        name: str,
        options: Dict[str, Any],
        custom_id: Optional[str] = None,
    ) -> STTInstanceConfig:
        await self._ensure_default_instances()
        instance_id = custom_id or f"stt_{uuid.uuid4().hex[:8]}"
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        content = STTInstanceFileContent(type=provider_type, name=name, options=options)
        file_path = self.backends_dir / f"{instance_id}.json"

        async with self._lock:
            await asyncio.to_thread(ConfigStore(STTInstanceFileContent, file_path).save, content)

        logger.info(f"Utworzono nową instancję STT [{name}] z ID: {instance_id}")
        return STTInstanceConfig(id=instance_id, **content.model_dump())

    async def update_instance(self, backend_id: str, options: Dict[str, Any]) -> STTInstanceConfig:
        """Nadpisuje `options` istniejącej instancji (typ/nazwa zostają) — używane przez
        shim kompatybilności `PUT /api/v1/voice/providers/config` (`voice/provider_routes.py`)."""
        await self._ensure_default_instances()
        sanitize_identifier(backend_id, field_name="backend_id")
        file_path = self.backends_dir / f"{backend_id}.json"

        async with self._lock:
            if not file_path.exists():
                raise ValueError(f"Instancja STT [{backend_id}] nie istnieje.")
            existing = await asyncio.to_thread(ConfigStore(STTInstanceFileContent, file_path).load)
            updated = existing.model_copy(update={"options": options})
            await asyncio.to_thread(ConfigStore(STTInstanceFileContent, file_path).save, updated)

        return STTInstanceConfig(id=backend_id, **updated.model_dump())

    async def load_all_instances(self) -> Dict[str, STTInstanceConfig]:
        await self._ensure_default_instances()
        instances: Dict[str, STTInstanceConfig] = {}

        async with self._lock:
            for file_path in self.backends_dir.glob("*.json"):
                try:
                    instance_id = file_path.stem
                    content = await asyncio.to_thread(ConfigStore(STTInstanceFileContent, file_path).load)
                    instances[instance_id] = STTInstanceConfig(id=instance_id, **content.model_dump())
                except Exception as e:
                    logger.error(f"Błąd podczas wczytywania pliku instancji STT [{file_path}]: {e}")

        return instances

    async def get_active_backend_id(self) -> str:
        await self._ensure_default_instances()
        async with self._lock:
            cfg = await asyncio.to_thread(
                self.active_store.load, default_factory=lambda: ActiveSTTBackendConfig(active_id=_DEFAULT_INSTANCE_ID)
            )
            return cfg.active_id

    async def set_active_backend_id(self, backend_id: str) -> None:
        sanitize_identifier(backend_id, field_name="backend_id")
        async with self._lock:
            await asyncio.to_thread(self.active_store.save, ActiveSTTBackendConfig(active_id=backend_id))
        logger.info(f"Zmieniono aktywną instancję STT na: [{backend_id}]")

    async def delete_instance(self, backend_id: str) -> bool:
        sanitize_identifier(backend_id, field_name="backend_id")
        await self._ensure_default_instances()
        async with self._lock:
            active_cfg = await asyncio.to_thread(
                self.active_store.load, default_factory=lambda: ActiveSTTBackendConfig(active_id=_DEFAULT_INSTANCE_ID)
            )
            if backend_id == active_cfg.active_id:
                raise ValueError(
                    f"Nie można usunąć aktywnej instancji STT [{backend_id}]. Najpierw przełącz na inną."
                )

            file_path = self.backends_dir / f"{backend_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Usunięto instancję STT [{backend_id}] z dysku.")
                return True
            return False

    async def get_active_provider(self) -> BaseSTTProvider:
        all_instances = await self.load_all_instances()

        if not all_instances:
            raise RuntimeError("Brak jakichkolwiek zadeklarowanych instancji STT w folderze data/stt_backends/")

        active_id = await self.get_active_backend_id()

        if active_id in all_instances:
            selected_config = all_instances[active_id]
        else:
            first_id = next(iter(all_instances.keys()))
            logger.warning(
                f"⚠️ Wskazane aktywne ID STT [{active_id}] nie istnieje na dysku. "
                f"Bezpieczne przełączenie na pierwszą dostępną instancję: [{first_id}]"
            )
            selected_config = all_instances[first_id]
            await self.set_active_backend_id(first_id)

        return STTFactory.create_provider(selected_config)
