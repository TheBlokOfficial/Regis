"""Magazyn profili promptu systemowego Świata Regis OS.

World jest jedynym autorem promptu tej tury, gdy jest podłączony (patrz
`agent/context_provider.py`, `ContextBuild.system_prompt`) — sam dokleja
aktywny profil (tożsamość) do dynamicznych faktów (`WorldEngine.build()`).
To dosłownie dawny, wieloprofilowy `PromptStore` z `agent/prompts/`,
przeniesiony 1:1 do World (który teraz faktycznie zarządza tożsamością),
z dodanym limitem `max_count=3` — World nie potrzebuje nieograniczonej
liczby przełączalnych profili, tylko garści (dom/praca/gość itp.).
"""

import asyncio
import uuid
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from shared import ConfigStore, get_logger, sanitize_identifier

logger = get_logger("regis.world.prompts")

_DEFAULT_PROFILE_ID = "profile_1"
_MAX_PROFILES = 3


class PromptFileContent(BaseModel):
    """Zawartość pojedynczego pliku JSON w <data_dir>/prompts/<id>.json."""

    name: str = Field(..., description="Wyświetlana nazwa profilu promptu")
    content: str = Field(..., description="Treść instrukcji systemowej (system prompt) — może być pusta")
    description: str | None = Field(default=None, description="Opcjonalny opis przeznaczenia profilu")


class PromptInstanceConfig(PromptFileContent):
    """Pełna konfiguracja instancji profilu promptu z ID, używana wewnętrznie."""

    id: str = Field(..., description="Unikalny identyfikator profilu (np. profile_1)")


class ActivePromptConfig(BaseModel):
    """Konfiguracja wskazująca aktywny profil — przechowywana w <data_dir>/active_prompt.json."""

    active_id: str = Field(..., description="ID aktualnie aktywnego profilu promptu")


class WorldPromptStore:
    """Menedżer przechowywania i zarządzania profilami promptu Świata.

    Profile zapisywane są jako pliki JSON w <data_dir>/prompts/<id>.json.
    Aktywny profil wskazywany jest przez plik <data_dir>/active_prompt.json.
    Jeśli katalog jest pusty, tworzy domyślny, PUSTY profil "Profil 1"
    (World nie dziedziczy tożsamości po kernelu — pusty profil oznacza
    "brak persony", tylko dynamiczne fakty).
    """

    def __init__(self, data_dir: Path) -> None:
        self.base_data_dir = data_dir.resolve()
        self.prompts_dir = self.base_data_dir / "prompts"
        self.active_config_path = self.base_data_dir / "active_prompt.json"

        self.active_store = ConfigStore(ActivePromptConfig, self.active_config_path)
        self._lock = asyncio.Lock()
        self._defaults_ensured = False

    async def ensure_defaults(self) -> None:
        """Tworzy domyślny, pusty profil jeśli katalog <data_dir>/prompts/ jest pusty. Wywołać przy starcie serwera."""
        if self._defaults_ensured:
            return
        async with self._lock:
            if self._defaults_ensured:
                return
            self.prompts_dir.mkdir(parents=True, exist_ok=True)
            existing = list(self.prompts_dir.glob("*.json"))
            if not existing:
                logger.info("Brak profili promptu Świata. Tworzenie pustego domyślnego profilu...")
                default_content = PromptFileContent(name="Profil 1", content="", description=None)
                file_path = self.prompts_dir / f"{_DEFAULT_PROFILE_ID}.json"
                await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).save, default_content)
                await asyncio.to_thread(
                    self.active_store.save, ActivePromptConfig(active_id=_DEFAULT_PROFILE_ID)
                )
                logger.info(f"Utworzono domyślny profil [{_DEFAULT_PROFILE_ID}] (pusty) i ustawiono jako aktywny.")
            self._defaults_ensured = True

    async def list_all(self) -> list[PromptInstanceConfig]:
        """Wczytuje i zwraca listę wszystkich profili z <data_dir>/prompts/."""
        await self.ensure_defaults()
        instances: list[PromptInstanceConfig] = []
        async with self._lock:
            for file_path in sorted(self.prompts_dir.glob("*.json")):
                try:
                    content = await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).load)
                    instances.append(PromptInstanceConfig(id=file_path.stem, **content.model_dump()))
                except Exception as e:
                    logger.error(f"Błąd podczas wczytywania pliku profilu promptu [{file_path}]: {e}")
        return instances

    async def get(self, prompt_id: str) -> PromptInstanceConfig | None:
        """Pobiera pojedynczy profil po ID lub None jeśli nie istnieje."""
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
        """Tworzy nowy profil i opcjonalnie ustawia go jako aktywny. Rzuca ValueError przy limicie 3 profili."""
        await self.ensure_defaults()
        prompt_id = custom_id or f"profile_{uuid.uuid4().hex[:8]}"
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        file_content = PromptFileContent(name=name, content=content, description=description)
        file_path = self.prompts_dir / f"{prompt_id}.json"
        async with self._lock:
            existing_count = len(list(self.prompts_dir.glob("*.json")))
            if existing_count >= _MAX_PROFILES:
                raise ValueError(f"Osiągnięto limit {_MAX_PROFILES} profili promptu Świata.")
            await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).save, file_content)
            if set_active:
                await asyncio.to_thread(self.active_store.save, ActivePromptConfig(active_id=prompt_id))
        logger.info(f"Utworzono nowy profil promptu [{name}] z ID: {prompt_id}" + (" (aktywny)" if set_active else ""))
        return PromptInstanceConfig(id=prompt_id, **file_content.model_dump())

    async def update(
        self,
        prompt_id: str,
        name: str | None = None,
        content: str | None = None,
        description: str | None = None,
    ) -> PromptInstanceConfig:
        """Aktualizuje wybrane pola istniejącego profilu. Rzuca ValueError jeśli nie istnieje."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        file_path = self.prompts_dir / f"{prompt_id}.json"
        if not file_path.exists():
            raise ValueError(f"Profil promptu o ID '{prompt_id}' nie istnieje.")
        async with self._lock:
            existing = await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).load)
            updated = PromptFileContent(
                name=name if name is not None else existing.name,
                content=content if content is not None else existing.content,
                description=description if description is not None else existing.description,
            )
            await asyncio.to_thread(ConfigStore(PromptFileContent, file_path).save, updated)
        logger.info(f"Zaktualizowano profil promptu [{prompt_id}].")
        return PromptInstanceConfig(id=prompt_id, **updated.model_dump())

    async def delete(self, prompt_id: str) -> bool:
        """Usuwa profil z dysku. Rzuca ValueError jeśli profil jest aktywny."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        await self.ensure_defaults()
        async with self._lock:
            active_id = await self._get_active_id_locked()
            if prompt_id == active_id:
                raise ValueError(
                    f"Nie można usunąć aktywnego profilu '{prompt_id}'. "
                    f"Najpierw aktywuj inny profil."
                )
            file_path = self.prompts_dir / f"{prompt_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Usunięto profil promptu [{prompt_id}] z dysku.")
                return True
        return False

    async def get_active_id(self) -> str:
        """Zwraca ID aktualnie aktywnego profilu."""
        await self.ensure_defaults()
        async with self._lock:
            return await self._get_active_id_locked()

    async def set_active(self, prompt_id: str) -> None:
        """Ustawia wskazany profil jako aktywny. Rzuca ValueError jeśli profil nie istnieje."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        await self.ensure_defaults()
        file_path = self.prompts_dir / f"{prompt_id}.json"
        if not file_path.exists():
            raise ValueError(f"Profil promptu o ID '{prompt_id}' nie istnieje.")
        async with self._lock:
            await asyncio.to_thread(self.active_store.save, ActivePromptConfig(active_id=prompt_id))
        logger.info(f"Ustawiono aktywny profil promptu: [{prompt_id}].")

    async def get_active_content(self) -> str | None:
        """Zwraca treść aktywnego profilu (może być pusty string) lub None jeśli nie udało się wczytać."""
        try:
            await self.ensure_defaults()
            active_id = await self.get_active_id()
            instance = await self.get(active_id)
            if instance:
                return instance.content
        except Exception as e:
            logger.warning(f"Nie udało się wczytać aktywnego profilu promptu Świata: {e}")
        return None

    async def _get_active_id_locked(self) -> str:
        """Wewnętrzna metoda odczytu active_id — wywoływać tylko wewnątrz bloku self._lock."""
        cfg = await asyncio.to_thread(
            self.active_store.load,
            default_factory=lambda: ActivePromptConfig(active_id=_DEFAULT_PROFILE_ID),
        )
        return cfg.active_id
