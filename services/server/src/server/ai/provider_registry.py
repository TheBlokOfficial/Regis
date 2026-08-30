"""Wspólna baza rejestrów dostawców AI — LLM, STT, TTS.

Trzy rejestry (`BackendRegistry`, `STTRegistry`, `TTSRegistry`) były swoimi
lustrami linia w linię: ten sam katalog plików JSON, ten sam wskaźnik aktywnej
instancji obok, to samo seedowanie przy pustym katalogu, ta sama awaryjna
podmiana aktywnego ID, gdy wskazuje na nieistniejący plik. Różniły się wyłącznie
nazwami typów i tekstami logów — i zdążyły się już rozjechać w sygnaturze
`update_instance`.

Podział odpowiedzialności:

* `shared.JsonInstanceRepository` — sam magazyn (pliki, lock, sanityzacja ID),
* `ProviderRegistry` (tu) — pojęcie **instancji aktywnej** + budowa konkretu
  przez fabrykę,
* podklasy (`ai/{llm,stt,tts}/registry.py`) — wyłącznie „czym jest ta domena":
  typy modeli, nazwy katalogów, prefiks ID i zestaw domyślnych instancji.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generic, Type, TypeVar

from shared import (
    ActiveInstancePointer,
    ConfigStore,
    JsonInstanceRepository,
    get_logger,
    resolve_secret_refs,
    sanitize_identifier,
)

from server.ai.provider_models import ProviderInstanceContent

logger = get_logger("regis.ai.registry")

TContent = TypeVar("TContent", bound=ProviderInstanceContent)
"""Zawartość pliku instancji: `{type, name, options}`."""

TInstance = TypeVar("TInstance", bound=ProviderInstanceContent)
"""To samo plus `id` odczytane z nazwy pliku — postać używana w pamięci serwera."""

TProvider = TypeVar("TProvider")
"""Gotowy konkret dostawcy (`BaseLLMProvider`/`BaseSTTProvider`/`BaseTTSProvider`)."""


class ProviderRegistry(ABC, Generic[TContent, TInstance, TProvider]):
    """Kolekcja nazwanych instancji dostawcy + wskaźnik aktualnie aktywnej."""

    def __init__(
        self,
        *,
        base_data_dir: Path,
        instances_dir_name: str,
        active_file_name: str,
        content_cls: Type[TContent],
        instance_cls: Type[TInstance],
        id_prefix: str,
        default_instance_id: str,
        label: str,
    ) -> None:
        """:param label: nazwa bytu w komunikatach, w dopełniaczu ("instancji STT").
        :param default_instance_id: ID, na które wskazuje wskaźnik aktywnej instancji,
            zanim cokolwiek zostanie zapisane — musi pokrywać się z jednym z ID
            tworzonych przez `_seed_default_instances()`.
        """
        self.base_data_dir = base_data_dir.resolve()
        self.instances_dir = self.base_data_dir / instances_dir_name
        self.active_config_path = self.base_data_dir / active_file_name
        self.active_store: ConfigStore[ActiveInstancePointer] = ConfigStore(
            ActiveInstancePointer, self.active_config_path
        )

        self._content_cls = content_cls
        self._instance_cls = instance_cls
        self._default_instance_id = default_instance_id
        self._label = label
        self._defaults_ensured = False
        self._repository: JsonInstanceRepository[TContent] = JsonInstanceRepository(
            directory=self.instances_dir,
            content_cls=content_cls,
            id_prefix=id_prefix,
            label=label,
        )

    # --------------------------------------------------------------------------
    # Do zdefiniowania przez domenę
    # --------------------------------------------------------------------------

    @abstractmethod
    async def _seed_default_instances(self) -> None:
        """Tworzy zestaw startowy, gdy katalog instancji jest pusty.

        Wołane raz, pod lockiem repozytorium — implementacja **nie może** wołać
        publicznych metod tej klasy (`asyncio.Lock` nie jest reentrantowy).
        Do zapisu służy `_write_seed()`.
        """

    @abstractmethod
    def _create_provider(self, config: TInstance) -> TProvider:
        """Buduje gotowy konkret dostawcy z konfiguracji instancji (fabryka domeny).

        **Nie wołaj tego wprost** — od budowania dostawcy jest `build_provider()`, które
        najpierw rozwiązuje referencje `env:NAZWA` w opcjach."""

    # --------------------------------------------------------------------------
    # Wspólna mechanika
    # --------------------------------------------------------------------------

    async def _write_seed(self, instance_id: str, content: TContent, *, set_active: bool = False) -> None:
        """Zapis instancji startowej z wnętrza `_seed_default_instances()` — bez
        nabywania locka, który w tym momencie jest już trzymany."""
        store: ConfigStore[TContent] = ConfigStore(self._content_cls, self._repository.path_for(instance_id))
        await asyncio.to_thread(store.save, content)
        if set_active:
            await asyncio.to_thread(self.active_store.save, ActiveInstancePointer(active_id=instance_id))

    async def _ensure_defaults(self) -> None:
        """Podwójne sprawdzenie flagi pod lockiem — eliminuje wyścig między
        równoległymi pierwszymi żądaniami, z których każde zastałoby pusty katalog."""
        if self._defaults_ensured:
            return
        async with self._repository.lock:
            if self._defaults_ensured:
                return
            await self._repository.ensure_directory()
            if await self._repository.is_empty():
                logger.info(f"Brak zadeklarowanych {self._label} — tworzenie zestawu startowego...")
                await self._seed_default_instances()
            self._defaults_ensured = True

    def _to_instance(self, instance_id: str, content: TContent) -> TInstance:
        # `model_validate` zamiast wywołania konstruktora: `id` (tu) i `type` (w
        # `create_instance`) są polami PODKLAS, nie wspólnej bazy `ProviderInstanceContent`
        # — konstruktor typowany po bazie ich nie zna. Walidacja jest ta sama.
        return self._instance_cls.model_validate({"id": instance_id, **content.model_dump()})

    def build_provider(self, config: TInstance) -> TProvider:
        """Gotowy konkret dostawcy — **jedyne** dopuszczalne wejście do fabryki domeny.

        Tutaj, i tylko tutaj, wartości `env:NAZWA` zamieniają się w prawdziwe sekrety
        (`shared/secrets.py`). Granica jest celowo postawiona na budowie konkretu, a nie
        na odczycie z dysku: `load_all_instances()` zasila też warstwę REST i CRUD, więc
        rozwiązana postać klucza nigdy nie może się tam pojawić. Jeden punkt obsługuje
        wszystkie trzy domeny (LLM/STT/TTS), bo prefiks referencji jest jednoznaczny
        i nie wymaga wiedzy o tym, które pole jest sekretne.
        """
        resolved = config.model_copy(update={"options": resolve_secret_refs(config.options)})
        return self._create_provider(resolved)

    async def create_instance(
        self,
        provider_type: Any,
        name: str,
        options: dict[str, Any],
        custom_id: str | None = None,
    ) -> TInstance:
        """Tworzy nową instancję i zapisuje ją jako plik JSON."""
        await self._ensure_defaults()
        content = self._content_cls.model_validate({"type": provider_type, "name": name, "options": options})
        instance_id = await self._repository.create(content, custom_id=custom_id)
        return self._to_instance(instance_id, content)

    async def update_instance(self, instance_id: str, name: str | None, options: dict[str, Any]) -> TInstance:
        """Nadpisuje nazwę i opcje istniejącej instancji. **Typ zostaje niezmienny** —
        jego zmiana unieważniłaby wszystkie opcje (inny zestaw pól, inny model), więc
        w praktyce jest to utworzenie innego presetu, nie edycja tego samego.

        `options` podmienia worek w całości; zachowywanie pominiętych sekretów
        rozstrzyga warstwa REST, która jako jedyna wie, które pola są sekretne —
        rejestr nie interpretuje zawartości worka.

        :raises ValueError: gdy instancja nie istnieje.
        """
        await self._ensure_defaults()
        existing = await self._repository.load(instance_id)
        if existing is None:
            raise ValueError(f"Instancja [{instance_id}] nie istnieje.")
        # Pominięta nazwa = "zachowaj obecną", wyrażone przez NIEDOŁOŻENIE klucza do
        # `update`, nie przez odczyt `existing.name` — dzięki temu magazyn nie musi
        # zakładać niczego o polach zawartości poza tym, że da się ją skopiować.
        changes: dict[str, Any] = {"options": options}
        if name:
            changes["name"] = name
        updated = existing.model_copy(update=changes)
        await self._repository.save(instance_id, updated)
        logger.info(f"Zaktualizowano {self._label} [{instance_id}].")
        return self._to_instance(instance_id, updated)

    async def load_all_instances(self) -> dict[str, TInstance]:
        """Wszystkie zadeklarowane instancje `{id: config}`."""
        await self._ensure_defaults()
        contents = await self._repository.load_all()
        return {iid: self._to_instance(iid, content) for iid, content in contents.items()}

    async def get_active_backend_id(self) -> str:
        await self._ensure_defaults()
        async with self._repository.lock:
            return (await self._load_active_pointer()).active_id

    async def set_active_backend_id(self, instance_id: str) -> None:
        sanitize_identifier(instance_id, field_name="instance_id")
        async with self._repository.lock:
            await asyncio.to_thread(self.active_store.save, ActiveInstancePointer(active_id=instance_id))
        logger.info(f"Zmieniono aktywną instancję [{self._label}] na: [{instance_id}]")

    async def delete_instance(self, instance_id: str) -> bool:
        """Usuwa plik instancji.

        Sprawdzenie „czy aktywna" i skasowanie dzieją się **pod jednym lockiem**,
        więc nie da się skasować instancji, która stała się aktywna między jednym
        a drugim.

        :raises ValueError: przy próbie usunięcia aktywnej instancji.
        """
        sanitize_identifier(instance_id, field_name="instance_id")
        await self._ensure_defaults()
        async with self._repository.lock:
            active_id = (await self._load_active_pointer()).active_id
            if instance_id == active_id:
                raise ValueError(
                    f"Nie można usunąć aktywnej instancji [{instance_id}]. Najpierw przełącz na inną."
                )
            return await self._repository.delete_unlocked(instance_id)

    async def get_active_provider(self) -> TProvider:
        """Gotowy konkret dla aktualnie aktywnej instancji.

        Gdy wskaźnik pokazuje na instancję, której nie ma na dysku (plik skasowany
        poza aplikacją), przełącza się awaryjnie na pierwszą dostępną i zapisuje
        poprawiony wskaźnik — zamiast wywracać każdą turę agenta.
        """
        all_instances = await self.load_all_instances()
        if not all_instances:
            raise RuntimeError(f"Brak jakichkolwiek zadeklarowanych {self._label} w [{self.instances_dir}].")

        active_id = await self.get_active_backend_id()
        if active_id in all_instances:
            selected = all_instances[active_id]
        else:
            first_id = next(iter(all_instances))
            logger.warning(
                f"Wskazane aktywne ID [{active_id}] nie istnieje na dysku. "
                f"Bezpieczne przełączenie na pierwszą dostępną instancję: [{first_id}]"
            )
            selected = all_instances[first_id]
            await self.set_active_backend_id(first_id)

        return self.build_provider(selected)

    async def _load_active_pointer(self) -> ActiveInstancePointer:
        """Odczyt wskaźnika **bez** nabywania locka — wołający już go trzyma."""
        return await asyncio.to_thread(
            self.active_store.load,
            default_factory=lambda: ActiveInstancePointer(active_id=self._default_instance_id),
        )
