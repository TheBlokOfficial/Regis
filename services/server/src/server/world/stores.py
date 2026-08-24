"""Trwałość Świata dla trzech bytów trzymanych w POJEDYNCZYCH plikach JSON:
konfiguracja Home Assistant, zadeklarowane urządzenia i rejestr klientów.

Kolekcje wieloplikowe (pokoje, grupy, profile promptu) idą przez
`shared.JsonInstanceRepository` — tutaj są byty, których jest z definicji po jednym.
Wspólny mianownik: `ConfigStore` + lock + `asyncio.to_thread`, powtórzony wcześniej
sześć razy wewnątrz `WorldEngine` w postaci par `get_*`/`_save_*`.

Magazyny **nie znają reguł domenowych** — „brak tokenu w żądaniu = zachowaj obecny"
albo „puste capabilities = zachowaj obecne" to decyzje silnika, nie zapisu na dysk.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Generic, Type, TypeVar

from pydantic import BaseModel
from shared import ConfigStore, get_logger

from server.world.models import (
    DeclaredDeviceEntry,
    DeclaredDevicesFileContent,
    HomeAssistantConfig,
    SenderProfile,
    SenderProfilesFileContent,
)

logger = get_logger("regis.world.stores")

TContent = TypeVar("TContent", bound=BaseModel)


class SingleFileStore(Generic[TContent]):
    """Jeden plik JSON = jeden byt. Brak pliku oznacza wartości domyślne modelu."""

    def __init__(self, path: Path, content_cls: Type[TContent], lock: asyncio.Lock) -> None:
        self._store: ConfigStore[TContent] = ConfigStore(content_cls, path)
        self._lock = lock

    async def load(self) -> TContent:
        return await asyncio.to_thread(self._store.load)

    async def save(self, content: TContent) -> None:
        async with self._lock:
            await asyncio.to_thread(self._store.save, content)


class HomeAssistantConfigStore(SingleFileStore[HomeAssistantConfig]):
    """Konfiguracja singletona Home Assistant (`base_url` + `access_token`).

    Puste pola oznaczają brak konfiguracji — `WorldEngine` degraduje się wtedy
    łagodnie (encje/narzędzia HA po prostu nie są dostarczane w danej turze),
    bez osobnego przełącznika `enabled`."""

    def __init__(self, path: Path, lock: asyncio.Lock) -> None:
        super().__init__(path, HomeAssistantConfig, lock)


class DeclaredDevicesStore(SingleFileStore[DeclaredDevicesFileContent]):
    """Zadeklarowana lista urządzeń — jedyne źródło prawdy o tym, co widzi agent.

    Model jest **opt-in**: brak wpisu oznacza niewidoczność, niezależnie od tego,
    czy encja istnieje po stronie HA."""

    def __init__(self, path: Path, lock: asyncio.Lock) -> None:
        super().__init__(path, DeclaredDevicesFileContent, lock)

    async def upsert(self, entity_id: str, entry: DeclaredDeviceEntry) -> None:
        current = await self.load()
        current.entries[entity_id] = entry
        await self.save(current)

    async def remove(self, entity_id: str) -> bool:
        current = await self.load()
        if entity_id not in current.entries:
            return False
        del current.entries[entity_id]
        await self.save(current)
        return True


class SenderProfilesStore(SingleFileStore[SenderProfilesFileContent]):
    """Rejestr klientów: `sender_id` -> pokój, nazwa i możliwości."""

    def __init__(self, path: Path, lock: asyncio.Lock) -> None:
        super().__init__(path, SenderProfilesFileContent, lock)

    async def upsert(self, sender_id: str, profile: SenderProfile) -> None:
        current = await self.load()
        current.entries[sender_id] = profile
        await self.save(current)

    async def remove(self, sender_id: str) -> bool:
        current = await self.load()
        if sender_id not in current.entries:
            return False
        del current.entries[sender_id]
        await self.save(current)
        return True
