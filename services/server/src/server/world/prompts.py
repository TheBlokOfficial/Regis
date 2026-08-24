"""Magazyn profili promptu systemowego Świata Regis OS.

World jest jedynym autorem promptu tej tury, gdy jest podłączony (patrz
`agent/context_provider.py`, `ContextBuild.system_prompt`) — sam dokleja
aktywny profil (tożsamość) do dynamicznych faktów (`WorldEngine.build()`).
To dosłownie dawny, wieloprofilowy `PromptStore` z `agent/prompts/`,
przeniesiony 1:1 do World (który teraz faktycznie zarządza tożsamością),
z dodanym limitem `max_count=3` — World nie potrzebuje nieograniczonej
liczby przełączalnych profili, tylko garści (dom/praca/gość itp.).

Mechanika plików (katalog, lock, sanityzacja ID, pomijanie uszkodzonych wpisów)
pochodzi z `shared.JsonInstanceRepository` — tutaj zostaje wyłącznie to, co
w profilach promptu jest inne niż w każdej innej kolekcji: limit trzech, aktualizacja
częściowa (pominięte pole = zachowaj obecne) i wskaźnik aktywnego profilu.
"""

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field
from shared import ActiveInstancePointer, ConfigStore, JsonInstanceRepository, get_logger, sanitize_identifier

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

        self.active_store: ConfigStore[ActiveInstancePointer] = ConfigStore(
            ActiveInstancePointer, self.active_config_path
        )
        self._repository: JsonInstanceRepository[PromptFileContent] = JsonInstanceRepository(
            directory=self.prompts_dir,
            content_cls=PromptFileContent,
            id_prefix="profile",
            label="profil promptu Świata",
        )
        self._defaults_ensured = False

    async def ensure_defaults(self) -> None:
        """Tworzy domyślny, pusty profil jeśli katalog <data_dir>/prompts/ jest pusty. Wywołać przy starcie serwera."""
        if self._defaults_ensured:
            return
        async with self._repository.lock:
            if self._defaults_ensured:
                return
            await self._repository.ensure_directory()
            if await self._repository.is_empty():
                logger.info("Brak profili promptu Świata. Tworzenie pustego domyślnego profilu...")
                store: ConfigStore[PromptFileContent] = ConfigStore(
                    PromptFileContent, self._repository.path_for(_DEFAULT_PROFILE_ID)
                )
                await asyncio.to_thread(
                    store.save, PromptFileContent(name="Profil 1", content="", description=None)
                )
                await asyncio.to_thread(
                    self.active_store.save, ActiveInstancePointer(active_id=_DEFAULT_PROFILE_ID)
                )
                logger.info(f"Utworzono domyślny profil [{_DEFAULT_PROFILE_ID}] (pusty) i ustawiono jako aktywny.")
            self._defaults_ensured = True

    async def list_all(self) -> list[PromptInstanceConfig]:
        """Wczytuje i zwraca listę wszystkich profili z <data_dir>/prompts/."""
        await self.ensure_defaults()
        contents = await self._repository.load_all()
        return [PromptInstanceConfig(id=pid, **content.model_dump()) for pid, content in contents.items()]

    async def get(self, prompt_id: str) -> PromptInstanceConfig | None:
        """Pobiera pojedynczy profil po ID lub None jeśli nie istnieje."""
        await self.ensure_defaults()
        content = await self._repository.load(prompt_id)
        if content is None:
            return None
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
        existing = await self._repository.load_all()
        if len(existing) >= _MAX_PROFILES:
            raise ValueError(f"Osiągnięto limit {_MAX_PROFILES} profili promptu Świata.")

        file_content = PromptFileContent(name=name, content=content, description=description)
        prompt_id = await self._repository.create(file_content, custom_id=custom_id)
        if set_active:
            await self.set_active(prompt_id)
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
        existing = await self._repository.load(prompt_id)
        if existing is None:
            raise ValueError(f"Profil promptu o ID '{prompt_id}' nie istnieje.")
        updated = PromptFileContent(
            name=name if name is not None else existing.name,
            content=content if content is not None else existing.content,
            description=description if description is not None else existing.description,
        )
        await self._repository.save(prompt_id, updated)
        logger.info(f"Zaktualizowano profil promptu [{prompt_id}].")
        return PromptInstanceConfig(id=prompt_id, **updated.model_dump())

    async def delete(self, prompt_id: str) -> bool:
        """Usuwa profil z dysku. Rzuca ValueError jeśli profil jest aktywny."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        await self.ensure_defaults()
        # Sprawdzenie "czy aktywny" i skasowanie pod JEDNYM lockiem — inaczej profil
        # mógłby stać się aktywny między jednym a drugim.
        async with self._repository.lock:
            if prompt_id == (await self._load_active_pointer()).active_id:
                raise ValueError(
                    f"Nie można usunąć aktywnego profilu '{prompt_id}'. Najpierw aktywuj inny profil."
                )
            return await self._repository.delete_unlocked(prompt_id)

    async def get_active_id(self) -> str:
        """Zwraca ID aktualnie aktywnego profilu."""
        await self.ensure_defaults()
        async with self._repository.lock:
            return (await self._load_active_pointer()).active_id

    async def set_active(self, prompt_id: str) -> None:
        """Ustawia wskazany profil jako aktywny. Rzuca ValueError jeśli profil nie istnieje."""
        sanitize_identifier(prompt_id, field_name="prompt_id")
        await self.ensure_defaults()
        if not self._repository.path_for(prompt_id).exists():
            raise ValueError(f"Profil promptu o ID '{prompt_id}' nie istnieje.")
        async with self._repository.lock:
            await asyncio.to_thread(self.active_store.save, ActiveInstancePointer(active_id=prompt_id))
        logger.info(f"Ustawiono aktywny profil promptu: [{prompt_id}].")

    async def get_active_content(self) -> str | None:
        """Zwraca treść aktywnego profilu (może być pusty string) lub None jeśli nie udało się wczytać."""
        try:
            active_id = await self.get_active_id()
            instance = await self.get(active_id)
            if instance:
                return instance.content
        except Exception as e:
            logger.warning(f"Nie udało się wczytać aktywnego profilu promptu Świata: {e}")
        return None

    async def _load_active_pointer(self) -> ActiveInstancePointer:
        """Odczyt wskaźnika **bez** nabywania locka — wołający już go trzyma."""
        return await asyncio.to_thread(
            self.active_store.load,
            default_factory=lambda: ActiveInstancePointer(active_id=_DEFAULT_PROFILE_ID),
        )
