"""Rejestr instancji backendów LLM. Cała mechanika (pliki, wskaźnik aktywnej
instancji, awaryjne przełączenie) mieszka w `ai/provider_registry.py` — tutaj
zostaje wyłącznie to, co odróżnia domenę LLM od STT/TTS."""

import asyncio
from pathlib import Path
from typing import Optional

from shared import ConfigStore, get_logger
from shared import data_dir as shared_data_dir

from server.ai.llm.factory import LLMFactory
from server.ai.llm.fallback_chain import FallbackChainConfig
from server.ai.llm.models import BackendFileContent, BackendInstanceConfig, ProviderType
from server.ai.provider_registry import ProviderRegistry
from server.ports.llm import BaseLLMProvider

logger = get_logger("regis.ai.llm.registry")

_DEFAULT_INSTANCE_ID = "bk_ollama_local"


class BackendRegistry(ProviderRegistry[BackendFileContent, BackendInstanceConfig, BaseLLMProvider]):
    """Menedżer instancji backendów LLM przechowywanych w plikach JSON w `data/backends/`."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        super().__init__(
            base_data_dir=data_dir or shared_data_dir(__file__),
            instances_dir_name="backends",
            active_file_name="active_backend.json",
            content_cls=BackendFileContent,
            instance_cls=BackendInstanceConfig,
            id_prefix="bk",
            default_instance_id=_DEFAULT_INSTANCE_ID,
            label="instancji backendu LLM",
        )
        self._chain_store: ConfigStore[FallbackChainConfig] = ConfigStore(
            FallbackChainConfig, self.base_data_dir / "fallback_chain.json"
        )

    def create_provider_instance(self, instance: BackendInstanceConfig) -> BaseLLMProvider:
        """Buduje konkret dla DOWOLNEJ instancji, nie tylko aktywnej — używane przez
        `LLMRouter` do rozwiązania każdego kandydata w łańcuchu fallbacku."""
        return self._create_provider(instance)

    async def get_fallback_chain(self) -> list[str]:
        """Uporządkowana lista ID presetów do prób, od najwyższego priorytetu.

        Pusta lista (domyślny stan) — wołający ma wtedy spaść z powrotem na
        pojedynczy `active_id`, dokładnie jak przed wprowadzeniem łańcucha."""
        config = await asyncio.to_thread(self._chain_store.load, default_factory=FallbackChainConfig)
        return config.priority_ids

    async def set_fallback_chain(self, priority_ids: list[str]) -> None:
        """:raises ValueError: gdy lista zawiera ID nieistniejącej instancji."""
        all_instances = await self.load_all_instances()
        unknown = [iid for iid in priority_ids if iid not in all_instances]
        if unknown:
            raise ValueError(f"Nieznane ID presetów w łańcuchu fallbacku: {unknown}")
        await asyncio.to_thread(self._chain_store.save, FallbackChainConfig(priority_ids=priority_ids))
        logger.info(f"Zaktualizowano łańcuch fallbacku LLM: {priority_ids}")

    async def delete_instance(self, instance_id: str) -> bool:
        """Usuwa instancję i, jeśli figurowała w łańcuchu fallbacku, czyści po niej ślad.

        Bez tego kasowanie presetu zostawiało martwy ID w `fallback_chain.json`
        na zawsze — pierwsza kolejna edycja priorytetu ZUPEŁNIE INNEGO presetu
        odsyłała ten martwy ID z powrotem i psuła cały zapis (`set_fallback_chain`
        odrzuca całość, gdy choć jeden ID jest nieznany). Bug zaobserwowany na
        żywo: toast "Nieznane ID presetów w łańcuchu fallbacku" przy edycji
        presetu, który nigdy nie był usuwany."""
        deleted = await super().delete_instance(instance_id)
        if deleted:
            chain = await self.get_fallback_chain()
            if instance_id in chain:
                await self.set_fallback_chain([iid for iid in chain if iid != instance_id])
        return deleted

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
