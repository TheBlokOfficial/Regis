"""Generyczny kontrakt granicy Sieć <-> Rozszerzenie.

Sieć zna wyłącznie ten protokół — nigdy konkretnego rozszerzenia (np. Home
Assistant). Rozszerzenie nie musi nawet importować tego modułu, wystarczy że
strukturalnie pasuje kształtem (typing.Protocol).
"""

from typing import Protocol

from fastapi import APIRouter


class NetworkExtension(Protocol):
    """Obecność sieciowa opcjonalnie dostarczana przez rozszerzenie."""

    extension_id: str
    """Stabilna tożsamość rozszerzenia — ten sam ciąg co `plugin_id` w
    `PluginProvider`, gdy rozszerzenie implementuje oba kontrakty."""

    label: str
    """Wyświetlana nazwa (np. do listy w zakładce „Rozszerzenia")."""

    async def is_enabled(self) -> bool:
        """Czy rozszerzenie aktywnie dostarcza wkład agentowi."""
        ...

    async def set_enabled(self, value: bool) -> None:
        """Włącza/wyłącza rozszerzenie."""
        ...

    def build_router(self) -> APIRouter:
        """Własny, w pełni gotowy router — sieć go montuje, nigdy nie zagląda do środka."""
        ...
