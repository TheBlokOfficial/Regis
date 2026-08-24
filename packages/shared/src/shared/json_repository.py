"""Magazyn „katalog plików JSON = kolekcja nazwanych instancji".

Wzorzec powtarzał się w projekcie **sześć razy**, linia w linię: rejestry
backendów LLM/STT/TTS (`server.ai`) oraz grupy urządzeń, pokoje i profile promptu
(`server.world`). Za każdym razem to samo: katalog, `ConfigStore` na plik,
`asyncio.Lock`, `sanitize_identifier` na identyfikatorze trafiającym do nazwy
pliku, `glob("*.json")` z pominięciem plików, których nie da się wczytać, i
`asyncio.to_thread` wokół każdej operacji dyskowej.

Kopiowanie zaczęło się rozjeżdżać (`update_instance` miało w LLM sygnaturę
`(id, name, options)`, a w STT/TTS `(id, options, name)`), co jest dokładnie tym
momentem, w którym duplikacja przestaje być tania.

**Zakres jest celowo wąski**: sam magazyn, bez pojęcia „instancji aktywnej",
bez fabryk i bez seedowania domyślnych wpisów — to warstwa wyżej
(`server.ai.provider_registry`), bo tylko część konsumentów jej potrzebuje.
Repozytorium operuje na *zawartości* pliku; złożenie `id` + zawartość w DTO
instancji zostaje po stronie wołającego, żeby magazyn nie musiał znać kształtu
cudzych modeli.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Generic, Type, TypeVar

from pydantic import BaseModel

from shared.config import ConfigStore, sanitize_identifier
from shared.logging import get_logger

logger = get_logger("regis.shared.repository")

TContent = TypeVar("TContent", bound=BaseModel)


class ActiveInstancePointer(BaseModel):
    """Wskaźnik aktywnej instancji — zawartość plików `active_*.json`.

    Jeden model na wszystkie trzy rejestry AI: format na dysku (`{"active_id": "..."}`)
    był w nich identyczny, a trzy osobne klasy różniły się wyłącznie tekstem opisu."""

    active_id: str


class JsonInstanceRepository(Generic[TContent]):
    """Kolekcja instancji trzymanych po jednym pliku JSON na wpis.

    Nazwa pliku (bez rozszerzenia) JEST identyfikatorem instancji — stąd
    `sanitize_identifier` przy każdej operacji przyjmującej ID z zewnątrz:
    bez tego `../../` w identyfikatorze wyszłoby poza katalog danych.
    """

    def __init__(
        self,
        directory: Path,
        content_cls: Type[TContent],
        id_prefix: str,
        label: str,
        lock: asyncio.Lock | None = None,
    ) -> None:
        """:param directory: katalog kolekcji (tworzony leniwie przy pierwszym zapisie).
        :param content_cls: model Pydantic zawartości pojedynczego pliku.
        :param id_prefix: prefiks generowanych identyfikatorów (np. `bk`, `room`).
        :param label: nazwa bytu w logach, w dopełniaczu (np. "instancji backendu LLM").
        :param lock: opcjonalnie współdzielony lock — pozwala kilku repozytoriom
            jednego właściciela (np. pokoje i grupy w `WorldEngine`) serializować
            zapisy na tym samym locku, tak jak robiły to przed wydzieleniem.
        """
        self.directory = directory
        self._content_cls = content_cls
        self._id_prefix = id_prefix
        self._label = label
        self._lock = lock or asyncio.Lock()

    @property
    def lock(self) -> asyncio.Lock:
        """Lock repozytorium — udostępniony, bo właściciele bywają zmuszeni objąć
        nim także własne operacje (np. odczyt wskaźnika aktywnej instancji, który
        musi być atomowy razem z kasowaniem pliku)."""
        return self._lock

    def path_for(self, instance_id: str) -> Path:
        return self.directory / f"{instance_id}.json"

    def generate_id(self) -> str:
        return f"{self._id_prefix}_{uuid.uuid4().hex[:8]}"

    async def ensure_directory(self) -> None:
        await asyncio.to_thread(self.directory.mkdir, parents=True, exist_ok=True)

    async def is_empty(self) -> bool:
        """True, gdy katalog nie istnieje albo nie ma w nim ani jednego pliku instancji."""
        if not self.directory.exists():
            return True
        return not any(self.directory.glob("*.json"))

    async def create(self, content: TContent, custom_id: str | None = None) -> str:
        """Zapisuje nową instancję i zwraca jej identyfikator.

        :raises ValueError: gdy `custom_id` nie jest bezpieczną nazwą pliku.
        """
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        instance_id = custom_id or self.generate_id()
        await self.ensure_directory()
        async with self._lock:
            await self._write(instance_id, content)
        logger.info(f"Utworzono {self._label} o ID: {instance_id}")
        return instance_id

    async def save(self, instance_id: str, content: TContent) -> None:
        """Upsert — nadpisuje albo tworzy instancję o podanym ID."""
        sanitize_identifier(instance_id, field_name="instance_id")
        await self.ensure_directory()
        async with self._lock:
            await self._write(instance_id, content)

    async def load(self, instance_id: str) -> TContent | None:
        """Zwraca zawartość instancji albo `None`, gdy plik nie istnieje."""
        sanitize_identifier(instance_id, field_name="instance_id")
        path = self.path_for(instance_id)
        if not path.exists():
            return None
        async with self._lock:
            return await self._read(path)

    async def load_all(self) -> dict[str, TContent]:
        """Zwraca `{id: zawartość}` posortowane po ID.

        Plik, którego nie da się wczytać (uszkodzony JSON, zmieniony schemat), jest
        **pomijany z wpisem w logu błędów**, nie wywraca całego odczytu — jedna
        popsuta instancja nie może odciąć użytkownika od pozostałych.
        """
        if not self.directory.exists():
            return {}
        result: dict[str, TContent] = {}
        async with self._lock:
            for path in sorted(self.directory.glob("*.json")):
                try:
                    result[path.stem] = await self._read(path)
                except Exception as err:
                    logger.error(f"Błąd podczas wczytywania pliku [{path}]: {err}")
        return result

    async def delete(self, instance_id: str) -> bool:
        """Usuwa plik instancji. Zwraca False, gdy nie istniał."""
        sanitize_identifier(instance_id, field_name="instance_id")
        async with self._lock:
            return await self._unlink(instance_id)

    async def delete_unlocked(self, instance_id: str) -> bool:
        """Wariant bez nabywania locka — dla właściciela, który już go trzyma
        (`asyncio.Lock` nie jest reentrantowy, więc zagnieżdżone `async with`
        zakleszczyłoby się na zawsze)."""
        sanitize_identifier(instance_id, field_name="instance_id")
        return await self._unlink(instance_id)

    # --------------------------------------------------------------------------
    # Operacje dyskowe — zawsze przez `asyncio.to_thread`, nigdy w pętli zdarzeń
    # --------------------------------------------------------------------------

    async def _write(self, instance_id: str, content: TContent) -> None:
        store: ConfigStore[TContent] = ConfigStore(self._content_cls, self.path_for(instance_id))
        await asyncio.to_thread(store.save, content)

    async def _read(self, path: Path) -> TContent:
        store: ConfigStore[TContent] = ConfigStore(self._content_cls, path)
        return await asyncio.to_thread(store.load)

    async def _unlink(self, instance_id: str) -> bool:
        path = self.path_for(instance_id)
        if not path.exists():
            return False
        await asyncio.to_thread(path.unlink)
        logger.info(f"Usunięto {self._label} [{instance_id}] z dysku.")
        return True
