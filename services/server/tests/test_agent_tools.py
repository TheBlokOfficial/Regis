import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest

from server.agent import AgentEngine
from server.agent.backend import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition, ToolResult
from server.agent.context.builder import ContextBuilder
from server.agent.gateway import Gateway
from server.agent.memory import MemoryManager
from server.agent.plugin_contract import EntityCapability, EntitySpec, Fact, PluginContribution
from server.plugins.datetime_plugin import DateTimePlugin
from server.plugins.smart_home.contract import DeviceIntegration
from server.plugins.smart_home.models import Device, DeviceGroup
from server.plugins.smart_home.plugin import SmartHomePlugin
from server.plugins.smart_home.registry import DeviceRegistry
from server.plugins.smart_home.tools import SmartHomeToolExecutor


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


def _make_raw_devices() -> list[Device]:
    """Urządzenia z natywnymi (nieprzestrzennymi) ID — dokładnie takie, jakie
    zwraca `DeviceIntegration.list_devices()`, zanim `SmartHomePlugin.build()`
    nada im przestrzeń nazw integracji."""
    return [
        Device(
            id="light.bathroom",
            integration_id="",
            name="Światło w łazience",
            kind="light",
            capabilities={"turn_on", "turn_off", "get_state"},
        ),
        Device(
            id="light.bathroom_mirror",
            integration_id="",
            name="Światło w łazience — lustro",
            kind="light",
            capabilities={"turn_on", "turn_off", "get_state"},
        ),
    ]


class FakeIntegration(DeviceIntegration):
    """Integracja testowa nagrywająca wywołania, bez żadnego realnego I/O."""

    def __init__(self, failing_device_id: str | None = None, devices: list[Device] | None = None) -> None:
        self.invocations: list[tuple[str, str]] = []
        self._failing_device_id = failing_device_id
        self._devices = devices or []

    async def list_devices(self) -> list[Device]:
        return list(self._devices)

    async def invoke(self, device_id: str, capability: str, **kwargs: Any) -> ToolResult:
        self.invocations.append((device_id, capability))
        if device_id == self._failing_device_id:
            return ToolResult(is_error=True, content="symulowany błąd urządzenia")
        return ToolResult(content=f"{capability} wykonane na {device_id}")


# --------------------------------------------------------------------------
# SmartHomeToolExecutor — capability gating, delegacja i częściowy sukces grupy
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_executor_rejects_capability_device_does_not_support():
    integration = FakeIntegration()
    device_registry = DeviceRegistry(_make_devices())
    executor = SmartHomeToolExecutor(device_registry, {"int_fake": integration})

    # Sensor nie deklaruje 'turn_on' — narzędzie musi odmówić bez wywoływania integracji.
    result = await executor.execute("turn_on", {"entity_id": "int_fake:sensor.living_room_temp"})

    assert result.is_error is True
    assert integration.invocations == []


@pytest.mark.anyio
async def test_executor_strips_integration_namespace_from_entity_ref():
    integration = FakeIntegration()
    device_registry = DeviceRegistry(_make_devices())
    executor = SmartHomeToolExecutor(device_registry, {"int_fake": integration})

    result = await executor.execute("turn_off", {"entity_id": "int_fake:light.bathroom"})

    assert result.is_error is False
    assert integration.invocations == [("light.bathroom", "turn_off")]


@pytest.mark.anyio
async def test_executor_reports_unknown_entity():
    integration = FakeIntegration()
    device_registry = DeviceRegistry(_make_devices())
    executor = SmartHomeToolExecutor(device_registry, {"int_fake": integration})

    result = await executor.execute("get_state", {"entity_id": "nieistniejący:ref"})

    assert result.is_error is True
    assert integration.invocations == []


@pytest.mark.anyio
async def test_executor_group_aggregates_partial_failure():
    integration = FakeIntegration(failing_device_id="light.bathroom_mirror")
    device_registry = DeviceRegistry(_make_devices(), [_make_group()])
    executor = SmartHomeToolExecutor(device_registry, {"int_fake": integration})

    result = await executor.execute("turn_on", {"entity_id": "grp_bathroom"})

    assert result.is_error is False  # częściowy sukces nie jest twardym błędem
    assert "1/2" in result.content
    assert set(integration.invocations) == {
        ("light.bathroom", "turn_on"),
        ("light.bathroom_mirror", "turn_on"),
    }


@pytest.mark.anyio
async def test_executor_group_with_missing_member_never_leaks_native_ref():
    integration = FakeIntegration()
    missing_group = DeviceGroup(
        id="grp_bathroom",
        name="Łazienka",
        device_ids=["int_fake:light.bathroom", "int_fake:light.nieistniejące"],
    )
    device_registry = DeviceRegistry(_make_devices(), [missing_group])
    executor = SmartHomeToolExecutor(device_registry, {"int_fake": integration})

    result = await executor.execute("turn_on", {"entity_id": "grp_bathroom"})

    # Raport o brakującym członku grupy nigdy nie ujawnia surowego, wewnętrznego
    # namespaced ref pluginu (format 'integration_id:native_id') — nawet ścieżką błędu.
    assert "int_fake:light.nieistniejące" not in result.content
    assert "nieznane urządzenie" in result.content


# --------------------------------------------------------------------------
# Gateway — opaque ID stabilny/deterministyczny, routing, kolizje narzędzi
# --------------------------------------------------------------------------


class FakePlugin:
    """PluginProvider testowy zwracający z góry zbudowany wkład, nagrywający dispatch."""

    def __init__(self, plugin_id: str, contribution: PluginContribution) -> None:
        self.plugin_id = plugin_id
        self._contribution = contribution
        self.received_facts: list[Fact] = []

    async def build(self, facts: list[Fact]) -> PluginContribution:
        self.received_facts = facts
        return self._contribution


def _entity_spec(ref: str, name: str, tool_names: tuple[str, ...]) -> EntitySpec:
    return EntitySpec(
        id=ref,
        name=name,
        capabilities=frozenset(EntityCapability(tool_name=t) for t in tool_names),
    )


@pytest.mark.anyio
async def test_gateway_opaque_id_is_deterministic_and_stable_across_builds():
    seen_refs: list[str] = []

    async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
        seen_refs.append(str(arguments.get("entity_id")))
        return ToolResult(content="ok")

    contribution = PluginContribution(
        tools=[ToolDefinition(name="ping", description="d", parameters={"type": "object", "properties": {}})],
        entities=[_entity_spec("native_ref_1", "Urządzenie testowe", ("ping",))],
        dispatch=dispatch,
    )
    plugin = FakePlugin("fake_plugin", contribution)
    gateway = Gateway(plugins=[plugin])

    build_1 = await gateway.build()
    build_2 = await gateway.build()

    assert build_1.entities[0].id == build_2.entities[0].id
    opaque_id = build_1.entities[0].id
    assert opaque_id != "native_ref_1"  # nieprzezroczysty — nie zdradza wewnętrznego ref


@pytest.mark.anyio
async def test_gateway_dispatch_translates_opaque_id_to_native_ref_before_calling_plugin():
    seen_refs: list[str] = []

    async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
        seen_refs.append(str(arguments.get("entity_id")))
        return ToolResult(content="ok")

    contribution = PluginContribution(
        tools=[ToolDefinition(name="ping", description="d", parameters={"type": "object", "properties": {}})],
        entities=[_entity_spec("native_ref_1", "Urządzenie testowe", ("ping",))],
        dispatch=dispatch,
    )
    plugin = FakePlugin("fake_plugin", contribution)
    gateway = Gateway(plugins=[plugin])

    build_result = await gateway.build()
    opaque_id = build_result.entities[0].id

    result = await build_result.dispatch("ping", {"entity_id": opaque_id})

    assert result.is_error is False
    assert seen_refs == ["native_ref_1"]  # plugin dostał wewnętrzny ref, nie opaque ID


@pytest.mark.anyio
async def test_gateway_dispatch_unknown_entity_id_returns_error():
    async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(content="nie powinno się wykonać")

    contribution = PluginContribution(
        tools=[ToolDefinition(name="ping", description="d", parameters={"type": "object", "properties": {}})],
        entities=[],
        dispatch=dispatch,
    )
    plugin = FakePlugin("fake_plugin", contribution)
    gateway = Gateway(plugins=[plugin])

    build_result = await gateway.build()
    result = await build_result.dispatch("ping", {"entity_id": "cokolwiek"})

    assert result.is_error is True


@pytest.mark.anyio
async def test_gateway_skips_colliding_tool_name_from_second_plugin():
    async def dispatch_first(name: str, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(content="pierwszy plugin")

    async def dispatch_second(name: str, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(content="nie powinno się wykonać — kolizja nazw")

    first = FakePlugin(
        "first",
        PluginContribution(
            tools=[ToolDefinition(name="turn_on", description="d1", parameters={"type": "object", "properties": {}})],
            entities=[],
            dispatch=dispatch_first,
        ),
    )
    second = FakePlugin(
        "second",
        PluginContribution(
            tools=[ToolDefinition(name="turn_on", description="d2", parameters={"type": "object", "properties": {}})],
            entities=[],
            dispatch=dispatch_second,
        ),
    )
    gateway = Gateway(plugins=[first, second])

    build_result = await gateway.build()

    assert len([d for d in build_result.tool_definitions if d.name == "turn_on"]) == 1
    result = await build_result.dispatch("turn_on", {})
    assert "nie powinno się wykonać" not in result.content


@pytest.mark.anyio
async def test_gateway_passes_facts_from_earlier_registered_plugin_to_later_one():
    async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(content="ok")

    first = FakePlugin(
        "first",
        PluginContribution(
            tools=[], entities=[], dispatch=dispatch, facts=[Fact(key="test_fact", value="test_value")]
        ),
    )
    second = FakePlugin("second", PluginContribution(tools=[], entities=[], dispatch=dispatch))

    gateway = Gateway(plugins=[first, second])
    build_result = await gateway.build()

    assert build_result.facts == [Fact(key="test_fact", value="test_value")]
    assert first.received_facts == []
    assert second.received_facts == [Fact(key="test_fact", value="test_value")]


@pytest.mark.anyio
async def test_gateway_plugin_built_first_never_sees_facts_from_plugin_built_after_it():
    async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(content="ok")

    first = FakePlugin("first", PluginContribution(tools=[], entities=[], dispatch=dispatch))
    second = FakePlugin(
        "second",
        PluginContribution(
            tools=[], entities=[], dispatch=dispatch, facts=[Fact(key="test_fact", value="test_value")]
        ),
    )

    # Odwrócona kolejność rejestracji względem poprzedniego testu: "second" jest
    # teraz budowany jako pierwszy plugin tej tury.
    gateway = Gateway(plugins=[second, first])
    await gateway.build()

    assert second.received_facts == []
    assert first.received_facts == [Fact(key="test_fact", value="test_value")]


# --------------------------------------------------------------------------
# ContextBuilder — kanały Encje/Fakty formatowane generycznie w system prompt
# --------------------------------------------------------------------------


def test_context_builder_formats_entities_and_facts_channels():
    builder = ContextBuilder(max_history_messages=None)

    messages = builder.build_messages(
        session_history=[],
        entities=[_entity_spec("opaque_abc", "Lampka", ("turn_on", "turn_off"))],
        facts=[Fact(key="aktualna_data_i_godzina", value="2026-08-14 12:00:00")],
    )

    system_content = messages[0].content
    assert "opaque_abc" in system_content
    assert "Lampka" in system_content
    assert "aktualna_data_i_godzina: 2026-08-14 12:00:00" in system_content


def test_context_builder_renders_granular_features_within_a_tool():
    builder = ContextBuilder(max_history_messages=None)
    entity = EntitySpec(
        id="opaque_light",
        name="Lampka salon",
        capabilities=frozenset(
            {
                EntityCapability(tool_name="get_state"),
                EntityCapability(tool_name="set_light", features=frozenset({"brightness"})),
            }
        ),
    )

    messages = builder.build_messages(session_history=[], entities=[entity])

    system_content = messages[0].content
    assert "set_light[brightness]" in system_content
    assert "get_state" in system_content


def test_context_builder_omits_empty_channels():
    builder = ContextBuilder(max_history_messages=None)

    messages = builder.build_messages(session_history=[])

    assert "Dostępne encje" not in messages[0].content
    assert "Znane fakty" not in messages[0].content


# --------------------------------------------------------------------------
# DateTimePlugin — symetria Fakt<->narzędzie (wizja, sekcja 4.5)
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_datetime_plugin_get_time_dispatch_matches_fact_value_from_same_build():
    plugin = DateTimePlugin()

    contribution = await plugin.build(facts=[])
    result = await contribution.dispatch("get_time", {})

    assert len(contribution.facts) == 1
    assert contribution.facts[0].key == "aktualna_data_i_godzina"
    assert result.is_error is False
    assert result.content == contribution.facts[0].value


# --------------------------------------------------------------------------
# Pełna pętla agentyczna (ReAct) w AgentEngine — Gateway + SmartHomePlugin end-to-end,
# bez śladu pluginu/integracji w odpowiedzi, adresowanie po opaque entity_id
# --------------------------------------------------------------------------


class ToolCallingMockProvider(BaseLLMProvider):
    """Pierwsza tura żąda wywołania narzędzia, druga zwraca finalną odpowiedź tekstową."""

    def __init__(self, tool_name: str, entity_id: str) -> None:
        self._model = "mock-tool-model"
        self._tool_name = tool_name
        self._entity_id = entity_id
        self.calls_seen: list[list[LLMMessage]] = []

    async def generate_stream(
        self,
        messages: List[LLMMessage],
        tools: list[ToolDefinition] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        self.calls_seen.append(messages)
        if len(self.calls_seen) == 1:
            yield ToolCallRequest(id="call_1", name=self._tool_name, arguments={"entity_id": self._entity_id})
        else:
            yield "Włączyłem światło."

    async def check_health(self) -> bool:
        return True


async def _setup_smart_home_plugin(tmp_dir: str) -> tuple[SmartHomePlugin, list[FakeIntegration], str]:
    """Rejestruje FakeIntegration w SmartHomePlugin i tworzy jedną włączoną instancję."""
    created: list[FakeIntegration] = []

    def factory(options: dict[str, Any]) -> FakeIntegration:
        integration = FakeIntegration(devices=_make_raw_devices())
        created.append(integration)
        return integration

    from shared import ProviderTypeSpecDTO

    plugin = SmartHomePlugin(data_dir=Path(tmp_dir) / "smart_home")
    plugin.register_integration_type("FAKE", factory, ProviderTypeSpecDTO(type="FAKE", label="Fake", options_schema=[]))
    integration_cfg = await plugin.create_integration_instance(
        provider_type="FAKE", name="Fake HA", options={}, enabled=True, custom_id="int_fake"
    )
    return plugin, created, integration_cfg.id


@pytest.mark.anyio
async def test_agent_engine_react_loop_turns_on_single_device_via_opaque_entity_id():
    with tempfile.TemporaryDirectory() as tmp_dir:
        plugin, created_integrations, integration_id = await _setup_smart_home_plugin(tmp_dir)
        gateway = Gateway(plugins=[plugin])

        # Odkrywamy opaque ID encji "Światło w łazience" tak, jak zrobiłby to agent
        # na podstawie kanału Encji w kontekście (osobne wywołanie build() — dowód
        # na deterministyczną stabilność opaque ID między turami).
        discovery_build = await gateway.build()
        target_entity = next(e for e in discovery_build.entities if e.name == "Światło w łazience")

        llm_provider = ToolCallingMockProvider(tool_name="turn_on", entity_id=target_entity.id)
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=llm_provider, memory_manager=memory_manager, gateway=gateway)

        chunks = [chunk async for chunk in engine.interact_stream(session_id="s1", prompt="Włącz światło w łazience")]

        integration = created_integrations[-1]
        assert integration.invocations == [("light.bathroom", "turn_on")]
        assert len(llm_provider.calls_seen) == 2
        second_turn_messages = llm_provider.calls_seen[1]
        assert any(m.role == "tool" and "turn_on wykonane" in m.content for m in second_turn_messages)
        assert "".join(chunks) == "Włączyłem światło."

        history = memory_manager.get_history(session_id="s1")
        assert history[-1].role == "assistant"
        assert history[-1].content == "Włączyłem światło."


@pytest.mark.anyio
async def test_agent_engine_react_loop_turns_on_group_with_partial_success_report():
    with tempfile.TemporaryDirectory() as tmp_dir:
        plugin, created_integrations, integration_id = await _setup_smart_home_plugin(tmp_dir)
        await plugin.create_group(
            name="Łazienka",
            device_ids=[f"{integration_id}:light.bathroom", f"{integration_id}:light.bathroom_mirror"],
            custom_id="grp_bathroom",
        )
        gateway = Gateway(plugins=[plugin])

        discovery_build = await gateway.build()
        group_entity = next(e for e in discovery_build.entities if e.name == "Łazienka")

        llm_provider = ToolCallingMockProvider(tool_name="turn_on", entity_id=group_entity.id)
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=llm_provider, memory_manager=memory_manager, gateway=gateway)

        _ = [chunk async for chunk in engine.interact_stream(session_id="s1", prompt="Włącz światła w łazience")]

        second_turn_messages = llm_provider.calls_seen[1]
        tool_result_message = next(m for m in second_turn_messages if m.role == "tool")
        assert "2/2" in tool_result_message.content
