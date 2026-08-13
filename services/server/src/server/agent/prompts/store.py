"""Magazyn promptów systemowych Agenta Regis OS.

Zarządza pełnym cyklem życia promptów: persystencją na dysku, CRUD oraz wyborem
aktywnego promptu systemowego przekazywanego do ContextBuilder.
Architektura wzorowana na BackendRegistry.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Optional

from shared import ConfigStore, get_logger, get_service_root, sanitize_identifier

from server.agent.context.builder import DEFAULT_SYSTEM_PROMPT
from server.agent.prompts.models import ActivePromptConfig, PromptFileContent, PromptInstanceConfig

logger = get_logger("regis.agent.prompts")

_DEFAULT_PROMPT_ID = "prompt_default"


class PromptStore:
    """Menedżer przechowywania i zarządzania promptami systemowymi Agenta.

    Prompty zapisywane są jako pliki JSON w data/prompts/<id>.json.
    Aktywny prompt wskazywany jest przez plik data/active_prompt.json.
    Jeśli katalog jest pusty, tworzy domyślny prompt z DEFAULT_SYSTEM_PROMPT jako fallback.
    """

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data")).resolve()
        self.prompts_dir = self.base_data_dir / "prompts"
        self.active_config_path = self.base_data_dir / "active_prompt.json"

        self.active_store = ConfigStore(ActivePromptConfig, self.active_config_path)
        self._lock = asyncio.Lock()
        self._defaults_ensured = False

    async def ensure_defaults(self) -> None:
        """Tworzy domyślny prompt jeśli katalog data/prompts/ jest pusty. Wywołać przy starcie serwera."""
        if self._defaults_ensured:
            return
        async with self._lock:
            if self._defaults_ensured:
                return
            self.prompts_dir.mkdir(parents=True, exist_ok=True)
            existing = list(self.prompts_dir.glob("*.json"))
            if not existing:
                logger.info("Brak promptów systemowych. Tworzenie domyślnego promptu...")
                default_content = PromptFileContent(
                    name="Domyślny Prompt Systemowy",
                    content=DEFAULT_SYSTEM_PROMPT,
                    description="Wbudowana instrukcja systemowa Agenta Regis OS.",
                )
                file_path = self.prompts_dir / f"{_DEFAULT_PROMPT_ID}.json"
                await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).save, default_content)
                await asyncio.to_thread(
                    self.active_store.save, ActivePromptConfig(active_id=_DEFAULT_PROMPT_ID)
                )
                logger.info(f"Utworzono domyślny prompt [{_DEFAULT_PROMPT_ID}] i ustawiono jako aktywny.")
            self._defaults_ensured = True

    async def list_all(self) -> list[PromptInstanceConfig]:
        """Wczytuje i zwraca listę wszystkich promptów z data/prompts/."""
        await self.ensure_defaults()
        instances: list[PromptInstanceConfig] = []
        async with self._lock:
            for file_path in sorted(self.prompts_dir.glob("*.json")):
                try:
                    content = await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).load)
                    instances.append(PromptInstanceConfig(id=file_path.stem, **content.model_dump()))
                except Exception as e:
                    logger.error(f"Błąd podczas wczytywania pliku promptu [{file_path}]: {e}")
        return instances

    async def get(self, prompt_id: str) -> PromptInstanceConfig | None:
        """Pobiera pojedynczy prompt po ID lub None jeśli nie istnieje."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        await self.ensure_defaults()
        file_path = self.prompts_dir / f"{prompt_id}.json"
        if not file_path.exists():
            return None
        async with self._lock:
            content = await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).load)
        return PromptInstanceConfig(id=prompt_id, **content.model_dump())

    async def create(
        self,
        name: str,
        content: str,
        description: str | None = None,
        custom_id: str | None = None,
        set_active: bool = False,
    ) -> PromptInstanceConfig:
        """Tworzy nowy prompt i opcjonalnie ustawia go jako aktywny."""
        prompt_id = custom_id or f"prompt_{uuid.uuid4().hex[:8]}"
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        file_content = PromptFileContent(name=name, content=content, description=description)
        file_path = self.prompts_dir / f"{prompt_id}.json"
        async with self._lock:
            await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).save, file_content)
            if set_active:
                await asyncio.to_thread(self.active_store.save, ActivePromptConfig(active_id=prompt_id))
        logger.info(f"Utworzono nowy prompt [{name}] z ID: {prompt_id}" + (" (aktywny)" if set_active else ""))
        return PromptInstanceConfig(id=prompt_id, **file_content.model_dump())

    async def update(
        self,
        prompt_id: str,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
    ) -> PromptInstanceConfig:
        """Aktualizuje wybrane pola istniejącego promptu. Rzuca ValueError jeśli nie istnieje."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        file_path = self.prompts_dir / f"{prompt_id}.json"
        if not file_path.exists():
            raise ValueError(f"Prompt o ID '{prompt_id}' nie istnieje.")
        async with self._lock:
            existing = await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).load)
            updated = PromptFileContent(
                name=name if name is not None else existing.name,
                content=content if content is not None else existing.content,
                description=description if description is not None else existing.description,
            )
            await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).save, updated)
        logger.info(f"Zaktualizowano prompt [{prompt_id}].")
        return PromptInstanceConfig(id=prompt_id, **updated.model_dump())

    async def delete(self, prompt_id: str) -> bool:
        """Usuwa prompt z dysku. Rzuca ValueError jeśli prompt jest aktywny."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        await self.ensure_defaults()
        async with self._lock:
            active_id = await self._get_active_id_locked()
            if prompt_id == active_id:
                raise ValueError(
                    f"Nie można usunąć aktywnego promptu '{prompt_id}'. "
                    f"Najpierw aktywuj inny prompt."
                )
            file_path = self.prompts_dir / f"{prompt_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Usunięto prompt [{prompt_id}] z dysku.")
                return True
        return False

    async def get_active_id(self) -> str:
        """Zwraca ID aktualnie aktywnego promptu."""
        await self.ensure_defaults()
        async with self._lock:
            return await self._get_active_id_locked()

    async def set_active(self, prompt_id: str) -> None:
        """Ustawia wskazany prompt jako aktywny. Rzuca ValueError jeśli prompt nie istnieje."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        await self.ensure_defaults()
        file_path = self.prompts_dir / f"{prompt_id}.json"
        if not file_path.exists():
            raise ValueError(f"Prompt o ID '{prompt_id}' nie istnieje.")
        async with self._lock:
            await asyncio.to_thread(self.active_store.save, ActivePromptConfig(active_id=prompt_id))
        logger.info(f"Ustawiono aktywny prompt: [{prompt_id}].")

    async def get_active_content(self) -> str | None:
        """Zwraca treść aktywnego promptu systemowego lub None jeśli nie udało się wczytać.

        Brak wyniku NIE jest błędem — AgentEngine użyje wtedy DEFAULT_SYSTEM_PROMPT z builder.py.
        """
        try:
            await self.ensure_defaults()
            active_id = await self.get_active_id()
            instance = await self.get(active_id)
            if instance:
                return instance.content
        except Exception as e:
            logger.warning(f"Nie udało się wczytać aktywnego promptu — używam fallbacku: {e}")
        return None

    async def _get_active_id_locked(self) -> str:
        """Wewnętrzna metoda odczytu active_id — wywoływać tylko wewnątrz bloku self._lock."""
        cfg = await asyncio.to_thread(
            self.active_store.load,
            default_factory=lambda: ActivePromptConfig(active_id=_DEFAULT_PROMPT_ID),
        )
        return cfg.active_id
