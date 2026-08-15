"""DateTimePlugin — minimalny `PluginProvider` dowodzący zasady symetrii
Fakt<->narzędzie (wizja, sekcja 4.5): jedno narzędzie (`get_time`) i jeden
odpowiadający mu Fakt, oba liczone z tego samego `datetime.now()`.
"""

from datetime import datetime
from typing import Any

from server.agent.backend import ToolDefinition, ToolResult
from server.agent.plugin_contract import Fact, PluginContribution

_TOOL_NAME = "get_time"
_FACT_KEY = "aktualna_data_i_godzina"


class DateTimePlugin:
    """Plugin daty/godziny — spełnia kontrakt `PluginProvider` Gateway."""

    plugin_id = "datetime"

    async def build(self, facts: list[Fact]) -> PluginContribution:
        del facts  # nieużywane — ten plugin nie potrzebuje Faktów innych pluginów

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
