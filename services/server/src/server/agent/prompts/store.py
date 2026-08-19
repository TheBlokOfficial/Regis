"""Magazyn fallbackowego promptu systemowego kernela Agenta Regis OS.

Jedna wartość, bez CRUD — używana wyłącznie gdy żaden silnik świata nie
dostarcza własnego `ContextBuild.system_prompt` (np. `NullWorldInterface`,
testy headless). Właściwy, edytowalny CRUD promptów (do 3 przełączalnych
profili) żyje dziś w `world/prompts.py` — World jest jedynym autorem
promptu, gdy jest podłączony.
"""

import asyncio
import json
from pathlib import Path
from typing import Optional

from shared import ConfigStore, get_logger, get_service_root

from server.agent.context.builder import DEFAULT_SYSTEM_PROMPT
from server.agent.prompts.models import AgentDefaultPromptConfig

logger = get_logger("regis.agent.prompts")


class AgentDefaultPromptStore:
    """Menedżer pojedynczej wartości — fallbackowego promptu systemowego kernela.

    Przechowywana jako data/agent_default_prompt.json. Przy pierwszym odczycie,
    jeśli plik nie istnieje, próbuje jednorazowej, best-effort migracji z
    legacy `data/prompts/<active_id>.json` (dawny wieloprofilowy `PromptStore`) —
    w przeciwnym razie zasiewa `DEFAULT_SYSTEM_PROMPT`. Legacy pliki pozostają
    nietknięte na dysku (nieużywane, nie kasujemy).
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data")).resolve()
        self.config_path = self.base_data_dir / "agent_default_prompt.json"
        self.store = ConfigStore(AgentDefaultPromptConfig, self.config_path)
        self._lock = asyncio.Lock()

    async def ensure_defaults(self) -> None:
        """Tworzy plik z wartością domyślną/migrowaną, jeśli jeszcze nie istnieje. Wywołać przy starcie serwera."""
        if self.config_path.exists():
            return
        async with self._lock:
            if self.config_path.exists():
                return
            content = await asyncio.to_thread(self._migrate_legacy_content) or DEFAULT_SYSTEM_PROMPT
            self.base_data_dir.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(self.store.save, AgentDefaultPromptConfig(content=content))
            logger.info("Utworzono fallbackowy prompt domyślny agenta.")

    def _migrate_legacy_content(self) -> str | None:
        """Best-effort, jednorazowa migracja z dawnego wieloprofilowego `PromptStore`."""
        legacy_active_path = self.base_data_dir / "active_prompt.json"
        legacy_prompts_dir = self.base_data_dir / "prompts"
        if not legacy_active_path.exists() or not legacy_prompts_dir.exists():
            return None
        try:
            active_id = json.loads(legacy_active_path.read_text(encoding="utf-8")).get("active_id")
            if not active_id:
                return None
            legacy_file = legacy_prompts_dir / f"{active_id}.json"
            if not legacy_file.exists():
                return None
            content = json.loads(legacy_file.read_text(encoding="utf-8")).get("content")
            if content:
                logger.info(f"Zmigrowano fallbackowy prompt agenta z legacy promptu [{active_id}].")
            return content
        except Exception as e:
            logger.warning(f"Migracja legacy promptu nie powiodła się — używam domyślnego: {e}")
            return None

    async def get_content(self) -> str:
        """Zwraca treść fallbackowego promptu systemowego (zawsze dostępna)."""
        await self.ensure_defaults()
        async with self._lock:
            cfg = await asyncio.to_thread(
                self.store.load, default_factory=lambda: AgentDefaultPromptConfig(content=DEFAULT_SYSTEM_PROMPT)
            )
        return cfg.content

    async def set_content(self, content: str) -> None:
        """Nadpisuje treść fallbackowego promptu systemowego."""
        await self.ensure_defaults()
        async with self._lock:
            await asyncio.to_thread(self.store.save, AgentDefaultPromptConfig(content=content))
        logger.info("Zaktualizowano fallbackowy prompt domyślny agenta.")
