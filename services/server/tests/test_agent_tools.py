import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest

from server.agent import AgentEngine
from server.agent.backend import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition, ToolResult
from server.agent.memory import MemoryManager
from server.addons.smart_home import DeviceIntegration
from server.addons.smart_home.devices import Device, DeviceGroup, DeviceRegistry
from server.addons.smart_home.tools import GetStateTool, TurnOffTool, TurnOnTool


def _make_devices() -> list[Device]:
    return [
        Device(
            id="int_fake:light.bathroom",
            integration_id="int_fake",
            name="Światło w łazience",
            kind="light",
            capabilities={"turn_on", "turn_off", "get_state"},
        ),
        Device(
            id="int_fake:light.bathroom_mirror",
            integration_id="int_fake",
            name="Światło w łazience — lustro",
            kind="light",
            capabilities={"turn_on", "turn_off", "get_state"},
        ),
        Device(
            id="int_fake:sensor.living_room_temp",
            integration_id="int_fake",
            name="Temperatura w salonie",
            kind="sensor",
            capabilities={"get_state"},
        ),
    ]


def _make_group() -> DeviceGroup:
    return DeviceGroup(
        id="grp_bathroom",
        name="Łazienka",
        device_ids=["int_fake:light.bathroom", "int_fake:light.bathroom_mirror"],
    )


# --------------------------------------------------------------------------
# DeviceRegistry.resolve — jedyne miejsce w systemie z logiką dopasowania nazwy
# --------------------------------------------------------------------------


def test_device_registry_resolve_exact_match():
    registry = DeviceRegistry(_make_devices())
    result = registry.resolve("Temperatura w salonie")
    assert isinstance(result, Device)
    assert result.id == "int_fake:sensor.living_room_temp"


def test_device_registry_resolve_ambiguous_partial_match():
    registry = DeviceRegistry(_make_devices())
    result = registry.resolve("łazience")
    assert isinstance(result, list)
    assert len(result) == 2


def test_device_registry_resolve_not_found():
    registry = DeviceRegistry(_make_devices())
    assert registry.resolve("kuchnia") is None


def test_device_registry_resolve_group_by_name():
    registry = DeviceRegistry(_make_devices(), [_make_group()])
    result = registry.resolve("Łazienka")
    assert isinstance(result, DeviceGroup)
    assert result.id == "grp_bathroom"


# --------------------------------------------------------------------------
# Narzędzia rdzenia addonu — capability gating i delegacja do właściwej integracji
# --------------------------------------------------------------------------


class FakeIntegration(DeviceIntegration):
    """Integracja testowa nagrywająca wywołania, bez żadnego realnego I/O."""

    def __init__(self, failing_device_id: str | None = None) -> None:
        self.invocations: list[tuple[str, str]] = []
        self._failing_device_id = failing_device_id

    async def list_devices(self) -> list[Device]:
        return []

    async def invoke(self, device_id: str, capability: str, **kwargs: Any) -> ToolResult:
        self.invocations.append((device_id, capability))
        if device_id == self._failing_device_id:
            return ToolResult(is_error=True, content="symulowany błąd urządzenia")
        return ToolResult(content=f"{capability} wykonane na {device_id}")


@pytest.mark.anyio
async def test_turn_on_tool_delegates_to_owning_integration():
    integration = FakeIntegration()
    device_registry = DeviceRegistry(_make_devices())
    tool = TurnOnTool(device_registry, {"int_fake": integration})

    result = await tool.execute({"name": "Temperatura w salonie"})

    # Sensor nie deklaruje 'turn_on' — narzędzie musi odmówić bez wywoływania integracji.
    assert result.is_error is True
    assert integration.invocations == []


@pytest.mark.anyio
async def test_turn_off_tool_strips_integration_namespace_from_device_id():
    integration = FakeIntegration()
    device_registry = DeviceRegistry(_make_devices())
    tool = TurnOffTool(device_registry, {"int_fake": integration})

    result = await tool.execute({"name": "Światło w łazience"})

    assert result.is_error is False
    assert integration.invocations == [("light.bathroom", "turn_off")]


@pytest.mark.anyio
async def test_get_state_tool_reports_unknown_device():
    integration = FakeIntegration()
    device_registry = DeviceRegistry(_make_devices())
    tool = GetStateTool(device_registry, {"int_fake": integration})

    result = await tool.execute({"name": "nieistniejące urządzenie"})

    assert result.is_error is True
    assert integration.invocations == []


@pytest.mark.anyio
async def test_turn_on_tool_on_group_aggregates_partial_failure():
    integration = FakeIntegration(failing_device_id="light.bathroom_mirror")
    device_registry = DeviceRegistry(_make_devices(), [_make_group()])
    tool = TurnOnTool(device_registry, {"int_fake": integration})

    result = await tool.execute({"name": "Łazienka"})

    assert result.is_error is False  # częściowy sukces nie jest twardym błędem
    assert "1/2" in result.content
    assert set(integration.invocations) == {
        ("light.bathroom", "turn_on"),
        ("light.bathroom_mirror", "turn_on"),
    }


# --------------------------------------------------------------------------
# Pełna pętla agentyczna (ReAct) w AgentEngine — bez śladu addonu/integracji w odpowiedzi
# --------------------------------------------------------------------------


class ToolCallingMockProvider(BaseLLMProvider):
    """Pierwsza tura żąda wywołania narzędzia, druga zwraca finalną odpowiedź tekstową."""

    def __init__(self, tool_name: str = "turn_on") -> None:
        self._model = "mock-tool-model"
        self._tool_name = tool_name
        self.calls_seen: list[list[LLMMessage]] = []

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        self.calls_seen.append(messages)
        if len(self.calls_seen) == 1:
            yield ToolCallRequest(id="call_1", name=self._tool_name, arguments={"name": "Światło w łazience"})
        else:
            yield "Włączyłem światło."

    async def check_health(self) -> bool:
        return True


class FakeAddonProvider:
    """Zaślepka AddonProvider zwracająca z góry zbudowany zestaw narzędzi (izolacja od IO/dysku)."""

    def __init__(self, tool_definitions, dispatch) -> None:
        self._tool_definitions = tool_definitions
        self._dispatch = dispatch

    async def build_tools(self):
        return self._tool_definitions, self._dispatch


@pytest.mark.anyio
async def test_agent_engine_react_loop_executes_tool_and_persists_final_text_only():
    integration = FakeIntegration()
    device_registry = DeviceRegistry(_make_devices())
    turn_on_tool = TurnOnTool(device_registry, {"int_fake": integration})

    async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
        assert name == "turn_on"
        return await turn_on_tool.execute(arguments)

    fake_addon = FakeAddonProvider([turn_on_tool.definition], dispatch)
    llm_provider = ToolCallingMockProvider()

    with tempfile.TemporaryDirectory() as tmp_dir:
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(
            llm_provider=llm_provider,
            memory_manager=memory_manager,
            addons=[fake_addon],  # type: ignore[list-item]
        )

        chunks = [chunk async for chunk in engine.interact_stream(session_id="s1", prompt="Włącz światło w łazience")]

    # Integracja została faktycznie wywołana...
    assert integration.invocations == [("light.bathroom", "turn_on")]
    # ...LLM dostał wynik narzędzia w drugiej turze...
    assert len(llm_provider.calls_seen) == 2
    second_turn_messages = llm_provider.calls_seen[1]
    assert any(m.role == "tool" and "turn_on wykonane" in m.content for m in second_turn_messages)
    # ...a użytkownik widzi tylko finalny tekst, bez śladu nazwy addonu/integracji.
    assert "".join(chunks) == "Włączyłem światło."

    history = memory_manager.get_history(session_id="s1")
    assert history[-1].role == "assistant"
    assert history[-1].content == "Włączyłem światło."


@pytest.mark.anyio
async def test_agent_engine_skips_colliding_tool_name_from_second_addon():
    integration = FakeIntegration()
    device_registry = DeviceRegistry(_make_devices())
    turn_on_tool = TurnOnTool(device_registry, {"int_fake": integration})

    async def dispatch_first(name: str, arguments: dict[str, Any]) -> ToolResult:
        return await turn_on_tool.execute(arguments)

    async def dispatch_second(name: str, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(content="nie powinno się wykonać — kolizja nazw")

    first_addon = FakeAddonProvider([turn_on_tool.definition], dispatch_first)
    colliding_def = ToolDefinition(name="turn_on", description="inny addon, ta sama nazwa", parameters={"type": "object", "properties": {}})
    second_addon = FakeAddonProvider([colliding_def], dispatch_second)

    with tempfile.TemporaryDirectory() as tmp_dir:
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(
            llm_provider=ToolCallingMockProvider(),
            memory_manager=memory_manager,
            addons=[first_addon, second_addon],  # type: ignore[list-item]
        )

        tool_defs, dispatch = await engine._build_aggregated_tools()

    # Tylko jedna definicja 'turn_on' trafia do LLM — ta z pierwszego zarejestrowanego addonu.
    assert len([d for d in tool_defs if d.name == "turn_on"]) == 1
    result = await dispatch("turn_on", {"name": "Światło w łazience"})
    assert "nie powinno się wykonać" not in result.content
