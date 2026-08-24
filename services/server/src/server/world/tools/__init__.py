"""Narzędzia, jakie Świat udostępnia agentowi.

* `home_assistant.py` — urządzenia (`get_state`/`turn_on`/`turn_off`), adresowane
  natywnym `entity_id`,
* `builtin.py` — narzędzia własne Świata (`get_time`, `speak_in_room`),
* `registry.py` — `ToolSet`: składa jedno i drugie w listę definicji + `dispatch`,
  czyli dokładnie to, czego oczekuje kernel.
"""

from server.world.tools.builtin import GET_TIME_TOOL, SPEAK_IN_ROOM_TOOL, get_time_tool, speak_in_room_tool
from server.world.tools.home_assistant import TOOL_NAMES, HomeAssistantToolExecutor, build_tool_definitions
from server.world.tools.registry import Tool, ToolSet

__all__ = [
    "GET_TIME_TOOL",
    "SPEAK_IN_ROOM_TOOL",
    "HomeAssistantToolExecutor",
    "TOOL_NAMES",
    "Tool",
    "ToolSet",
    "build_tool_definitions",
    "get_time_tool",
    "speak_in_room_tool",
]
