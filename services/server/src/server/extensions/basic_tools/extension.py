"""BasicToolsExtension — minimalne rozszerzenie dowodzące zasady symetrii
Fakt<->narzędzie: jedno narzędzie (`get_time`) i jeden odpowiadający mu Fakt,
oba liczone z tego samego `datetime.now()`.

Migracja dawnego `plugins/datetime_plugin.py::DateTimePlugin` do wzorca
Rozszerzeń — ta sama logika, plus enable/disable przez `state.json` (ten sam
mechanizm co `HomeAssistantExtension`).
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter
from shared import ConfigStore, get_service_root

from server.agent.backend import ToolDefinition, ToolResult
from server.agent.plugin_contract import Fact, PluginContribution
from server.extensions._shared.state import ExtensionStateFileContent

_TOOL_NAME = "get_time"
_FACT_KEY = "aktualna_data_i_godzina"


class BasicToolsExtension:
    """Rozszerzenie podstawowych narzędzi — spełnia `PluginProvider` i `NetworkExtension`."""

    plugin_id = "basic_tools"
    extension_id = "basic_tools"
    label = "Podstawowe narzędzia"

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        service_root = get_service_root(__file__)
        self.base_data_dir = (data_dir or (service_root / "data" / "extensions" / "basic_tools")).resolve()
        self.state_path = self.base_data_dir / "state.json"

    async def is_enabled(self) -> bool:
        state = await asyncio.to_thread(ConfigStore(ExtensionStateFileContent, self.state_path).load)
        return state.enabled

    async def set_enabled(self, value: bool) -> None:
        await asyncio.to_thread(ConfigStore(ExtensionStateFileContent, self.state_path).save, ExtensionStateFileContent(enabled=value))

    def build_router(self) -> APIRouter:
        """Brak własnych endpointów domenowych — enable/disable obsługuje w pełni
        generyczny rejestr rozszerzeń (`PUT /api/v1/extensions/{id}`)."""
        return APIRouter()

    async def build(self, facts: list[Fact]) -> PluginContribution:
        del facts  # nieużywane — to rozszerzenie nie potrzebuje Faktów innych rozszerzeń

        if not await self.is_enabled():
            async def _disabled_dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
                return ToolResult(is_error=True, content=f"Rozszerzenie Podstawowe narzędzia jest wyłączone — narzędzie '{name}' niedostępne.")

            return PluginContribution(tools=[], entities=[], dispatch=_disabled_dispatch)

        now_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
            del arguments
            if name != _TOOL_NAME:
                return ToolResult(is_error=True, content=f"Nieznane narzędzie: '{name}'.")
            return ToolResult(content=now_value)

        return PluginContribution(
            tools=[
                ToolDefinition(
                    name=_TOOL_NAME,
                    description="Zwraca aktualną datę i godzinę.",
                    parameters={"type": "object", "properties": {}},
                )
            ],
            entities=[],
            dispatch=dispatch,
            facts=[Fact(key=_FACT_KEY, value=now_value)],
        )
