"""Konfiguracja kolejności presetów LLM w łańcuchu fallbacku.

Osobny plik/model od `ActiveInstancePointer` (`active_backend.json`) — celowo:
`active_id` dalej znaczy to, co dziś w całym `ProviderRegistry` (preset do
edycji/podglądu w CRUD), łańcuch to nakładka na runtime routera, nie zamiennik
tego pojęcia. Pusta lista = zachowanie nierozróżnialne od stanu sprzed
wprowadzenia łańcucha (`LLMRouter` używa wtedy wyłącznie `active_id`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FallbackChainConfig(BaseModel):
    priority_ids: list[str] = Field(
        default_factory=list, description="ID presetów LLM w kolejności prób, od najwyższego priorytetu"
    )
