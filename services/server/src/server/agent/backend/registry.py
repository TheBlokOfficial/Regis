import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from shared import ConfigStore, get_service_root, get_logger

from server.agent.backend.factory import LLMFactory
from server.agent.backend.models import ActiveBackendConfig, BackendFileContent, BackendInstanceConfig, ProviderType
from server.agent.backend.providers import BaseLLMProvider

logger = get_logger("regis.agent.backends.registry")


class BackendRegistry:
    """Menedżer zarządzenia instancjami backendów LLM przechowywanymi w plikach JSON w data/."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data")).resolve()
        self.backends_dir = self.base_data_dir / "backends"
        self.active_config_path = self.base_data_dir / "active_backend.json"

        self.active_store = ConfigStore(ActiveBackendConfig, self.active_config_path)

    def create_instance(
        self,
        provider_type: ProviderType,
        name: str,
        options: Dict[str, Any],
        custom_id: Optional[str] = None,
    ) -> BackendInstanceConfig:
        """Tworzy nową skonfigurowaną instancję backendu i zapisuje ją w pliku JSON w data/backends/.

        :param provider_type: Typ dostawcy (OLLAMA, OPENROUTER, OPENAI).
        :param name: Wyświetlana nazwa instancji.
        :param options: Worek z opcjami dostawcy.
        :param custom_id: Opcjonalny własny identyfikator (jeśli brak, generowany jest bk_<8_hex>).
        :return: Utworzona instancja BackendInstanceConfig.
        """
        instance_id = custom_id or f"bk_{uuid.uuid4().hex[:8]}"
        content = BackendFileContent(
            type=provider_type,
            name=name,
            options=options,
        )

        file_path = self.backends_dir / f"{instance_id}.json"
        ConfigStore(BackendFileContent, file_path).save(content)
        logger.info(f"Utworzono nową instancję backendu [{name}] z ID: {instance_id}")

        return BackendInstanceConfig(id=instance_id, **content.model_dump())

    def _ensure_default_instances(self) -> None:
        """Tworzy domyślne początkowe pliki instancji backendów, jeśli folder jest pusty."""
        self.backends_dir.mkdir(parents=True, exist_ok=True)
        existing_files = list(self.backends_dir.glob("*.json"))

        if not existing_files:
            logger.info("Brak zadeklarowanych instancji backendów. Tworzenie instancji domyślnych...")

            # 1. Domyślna instancja Ollamy
            ollama_id = "bk_ollama_local"
            ollama_content = BackendFileContent(
                type=ProviderType.OLLAMA,
                name="Lokalna Ollama (Llama 3)",
                options={
                    "base_url": "http://localhost:11434",
                    "model": "llama3",
                    "timeout": 30.0,
                },
            )
            ConfigStore(BackendFileContent, self.backends_dir / f"{ollama_id}.json").save(ollama_content)

            # 2. Domyślny szablon instancji OpenRoutera
            openrouter_id = "bk_openrouter_main"
            openrouter_content = BackendFileContent(
                type=ProviderType.OPENROUTER,
                name="OpenRouter (Claude 3.5 Sonnet)",
                options={
                    "api_key": "",
                    "model": "anthropic/claude-3.5-sonnet",
                    "base_url": "https://openrouter.ai/api/v1",
                    "timeout": 30.0,
                },
            )
            ConfigStore(BackendFileContent, self.backends_dir / f"{openrouter_id}.json").save(openrouter_content)

            # Zapisanie domyślnie aktywnej instancji
            self.active_store.save(ActiveBackendConfig(active_id=ollama_id))

    def load_all_instances(self) -> Dict[str, BackendInstanceConfig]:
        """Wczytuje i zwraca słownik wszystkich dostępnych instancji backendów {id: config}."""
        self._ensure_default_instances()
        instances: Dict[str, BackendInstanceConfig] = {}

        for file_path in self.backends_dir.glob("*.json"):
            try:
                instance_id = file_path.stem
                store = ConfigStore(BackendFileContent, file_path)
                content = store.load()
                instance_config = BackendInstanceConfig(id=instance_id, **content.model_dump())
                instances[instance_id] = instance_config
            except Exception as e:
                logger.error(f"Błąd podczas wczytywania pliku instancji backendu [{file_path}]: {e}")

        return instances

    def get_active_backend_id(self) -> str:
        """Wczytuje ID obecnie aktywnego backendu z pliku active_backend.json."""
        self._ensure_default_instances()
        cfg = self.active_store.load(default_factory=lambda: ActiveBackendConfig(active_id="bk_ollama_local"))
        return cfg.active_id

    def set_active_backend_id(self, backend_id: str) -> None:
        """Ustawia i zapisuje ID aktywnego backendu w pliku active_backend.json."""
        self.active_store.save(ActiveBackendConfig(active_id=backend_id))
        logger.info(f"Zmieniono aktywną instancję backendu na: [{backend_id}]")

    def get_active_provider(self) -> BaseLLMProvider:
        """Zwraca gotową instancję BaseLLMProvider dla obecnie aktywnego backendu.

        W przypadku braku aktywnego ID lub braku dopasowanego pliku, bezpiecznie
        wybiera pierwszą dostępną instancję.
        """
        all_instances = self.load_all_instances()

        if not all_instances:
            raise RuntimeError("Brak jakichkolwiek zadeklarowanych instancji backendu w folderze data/backends/")

        active_id = self.get_active_backend_id()

        selected_config: Optional[BackendInstanceConfig] = None

        if active_id in all_instances:
            selected_config = all_instances[active_id]
        else:
            first_id = next(iter(all_instances.keys()))
            logger.warning(
                f"⚠️ Wskazane aktywne ID [{active_id}] nie istnieje na dysku. "
                f"Bezpieczne przełączenie na pierwszą dostępną instancję: [{first_id}]"
            )
            selected_config = all_instances[first_id]
            self.set_active_backend_id(first_id)

        return LLMFactory.create_provider(selected_config)
