"""Rejestr instancji backendów LLM. Cała mechanika (pliki, wskaźnik aktywnej
instancji, awaryjne przełączenie) mieszka w `ai/provider_registry.py` — tutaj
zostaje wyłącznie to, co odróżnia domenę LLM od STT/TTS."""

from pathlib import Path
from typing import Optional

from shared import get_service_root

from server.ai.llm.factory import LLMFactory
from server.ai.llm.models import BackendFileContent, BackendInstanceConfig, ProviderType
from server.ai.provider_registry import ProviderRegistry
from server.ports.llm import BaseLLMProvider

_DEFAULT_INSTANCE_ID = "bk_ollama_local"


class BackendRegistry(ProviderRegistry[BackendFileContent, BackendInstanceConfig, BaseLLMProvider]):
    """Menedżer instancji backendów LLM przechowywanych w plikach JSON w `data/backends/`."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        super().__init__(
            base_data_dir=data_dir or (get_service_root(__file__) / "data"),
            instances_dir_name="backends",
            active_file_name="active_backend.json",
            content_cls=BackendFileContent,
            instance_cls=BackendInstanceConfig,
            id_prefix="bk",
            default_instance_id=_DEFAULT_INSTANCE_ID,
            label="instancji backendu LLM",
        )

    async def _seed_default_instances(self) -> None:
        """Dwie instancje startowe: lokalna Ollama (aktywna — działa bez żadnego
        klucza API) i pusty preset OpenRouter gotowy na wklejenie klucza."""
        await self._write_seed(
            _DEFAULT_INSTANCE_ID,
            BackendFileContent(
                type=ProviderType.OLLAMA,
                name="Lokalna Ollama (Llama 3)",
                options={"base_url": "http://localhost:11434", "model": "llama3"},
            ),
            set_active=True,
        )
        await self._write_seed(
            "bk_openrouter_main",
            BackendFileContent(
                type=ProviderType.OPENROUTER,
                name="OpenRouter (Claude 3.5 Sonnet)",
                options={"api_key": "", "model": "anthropic/claude-3.5-sonnet"},
            ),
        )

    def _create_provider(self, config: BackendInstanceConfig) -> BaseLLMProvider:
        return LLMFactory.create_provider(config)
