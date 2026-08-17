import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from server.agent import AgentEngine
from server.agent.backend import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition, ToolResult
from server.agent.context.builder import ContextBuilder
from server.agent.gateway import Gateway
from server.agent.memory import MemoryManager
from server.agent.plugin_contract import EntityCapability, EntitySpec, Fact, PluginContribution
from server.extensions.basic_tools import BasicToolsExtension
from server.extensions.home_assistant import HomeAssistantExtension
from server.extensions.home_assistant.models import (
    Device,
    DeviceGroup,
    HomeAssistantConfig,
)
from server.extensions.home_assistant.registry import DeviceRegistry
from server.extensions.home_assistant.tools import HomeAssistantToolExecutor
from server.network.extension_contract import NetworkExtension
from server.network.gateway import create_gateway_app
from server.network.routes.extensions import create_extensions_registry_router


_CORE_CAPS = {"turn_on": frozenset(), "turn_off": frozenset(), "get_state": frozenset()}


def _make_devices() -> list[Device]:
    return [
        Device(
            id="light.bathroom",
            name="Światło w łazience",
            kind="light",
            capabilities=dict(_CORE_CAPS),
        ),
        Device(
            id="light.bathroom_mirror",
            name="Światło w łazience — lustro",
            kind="light",
            capabilities=dict(_CORE_CAPS),
        ),
        Device(
            id="sensor.living_room_temp",
            name="Temperatura w salonie",
            kind="sensor",
            capabilities={"get_state": frozenset()},
        ),
    ]


def _make_group() -> DeviceGroup:
    return DeviceGroup(
        id="grp_bathroom",
        name="Łazienka",
        device_ids=["light.bathroom", "light.bathroom_mirror"],
    )


def _make_raw_devices() -> list[Device]:
    """Urządzenia dokładnie takie, jakie zwraca `HomeAssistantClient.list_devices()`."""
    return [
        Device(
            id="light.bathroom",
            name="Światło w łazience",
            kind="light",
            capabilities=dict(_CORE_CAPS),
        ),
        Device(
            id="light.bathroom_mirror",
            name="Światło w łazience — lustro",
            kind="light",
            capabilities=dict(_CORE_CAPS),
        ),
    ]


class FakeHomeAssistantClient:
    """Klient testowy nagrywający wywołania, bez żadnego realnego I/O."""

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
# HomeAssistantToolExecutor — capability gating, delegacja i częściowy sukces grupy
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_executor_rejects_capability_device_does_not_support():
    client = FakeHomeAssistantClient()
    device_registry = DeviceRegistry(_make_devices())
    executor = HomeAssistantToolExecutor(device_registry, client)

    # Sensor nie deklaruje 'turn_on' — narzędzie musi odmówić bez wywoływania klienta.
    result = await executor.execute("turn_on", {"entity_id": "sensor.living_room_temp"})

    assert result.is_error is True
    assert client.invocations == []


@pytest.mark.anyio
async def test_executor_invokes_device_by_native_entity_id():
    client = FakeHomeAssistantClient()
    device_registry = DeviceRegistry(_make_devices())
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute("turn_off", {"entity_id": "light.bathroom"})

    assert result.is_error is False
    assert client.invocations == [("light.bathroom", "turn_off")]


@pytest.mark.anyio
async def test_executor_reports_unknown_entity():
    client = FakeHomeAssistantClient()
    device_registry = DeviceRegistry(_make_devices())
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute("get_state", {"entity_id": "nieistniejący.ref"})

    assert result.is_error is True
    assert client.invocations == []


@pytest.mark.anyio
async def test_executor_group_aggregates_partial_failure():
    client = FakeHomeAssistantClient(failing_device_id="light.bathroom_mirror")
    device_registry = DeviceRegistry(_make_devices(), [_make_group()])
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute("turn_on", {"entity_id": "grp_bathroom"})

    assert result.is_error is False  # częściowy sukces nie jest twardym błędem
    assert "1/2" in result.content
    assert set(client.invocations) == {
        ("light.bathroom", "turn_on"),
        ("light.bathroom_mirror", "turn_on"),
    }


@pytest.mark.anyio
async def test_executor_group_with_missing_member_never_leaks_raw_ref():
    client = FakeHomeAssistantClient()
    missing_group = DeviceGroup(
        id="grp_bathroom",
        name="Łazienka",
        device_ids=["light.bathroom", "light.nieistniejące"],
    )
    device_registry = DeviceRegistry(_make_devices(), [missing_group])
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute("turn_on", {"entity_id": "grp_bathroom"})

    # Raport o brakującym członku grupy nigdy nie ujawnia surowego ref-a
    # brakującego urządzenia — nawet ścieżką błędu.
    assert "light.nieistniejące" not in result.content
    assert "nieznane urządzenie" in result.content


# --------------------------------------------------------------------------
# Dekoder capabilities domeny 'light' i walidacja opcjonalnych pól 'turn_on'
# w executorze (jasność/kolor/efekt to parametry turn_on, nie osobne narzędzia
# — light/turn_on w HA przyjmuje je wszystkie w jednym wywołaniu).
# --------------------------------------------------------------------------


def test_decode_light_infers_brightness_and_color_from_color_modes():
    from server.extensions.home_assistant.client import _decode_light

    # supported_features=44 kodowałby EFFECT, ale bez effect_list cecha nie powstaje.
    caps = _decode_light({"supported_color_modes": ["color_temp", "hs", "rgb"], "supported_features": 44})

    assert set(caps) == {"turn_on", "turn_off", "get_state"}
    assert caps["turn_on"] == frozenset({"brightness", "color_temp", "hs", "rgb"})


def test_decode_light_adds_effect_feature_when_effect_list_present():
    from server.extensions.home_assistant.client import _decode_light

    caps = _decode_light({"supported_color_modes": ["onoff"], "supported_features": 4, "effect_list": ["rainbow"]})

    assert "effect" in caps["turn_on"]


def test_decode_light_ignores_legacy_supported_features_bits():
    from server.extensions.home_assistant.client import _decode_light

    # Bitmaska sugeruje legacy brightness/color, ale supported_color_modes mówi 'onoff' —
    # dekoder ma ufać wyłącznie color_modes.
    caps = _decode_light({"supported_color_modes": ["onoff"], "supported_features": 63})

    assert caps["turn_on"] == frozenset()


@pytest.mark.anyio
async def test_executor_turn_on_rejects_both_color_params_given():
    client = FakeHomeAssistantClient()
    device = Device(
        id="light.rgb",
        name="Lampa RGB",
        kind="light",
        capabilities={**_CORE_CAPS, "turn_on": frozenset({"rgb", "color_temp"})},
    )
    device_registry = DeviceRegistry([device])
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute(
        "turn_on", {"entity_id": "light.rgb", "color_temp_kelvin": 4000, "rgb_color": [255, 0, 0]}
    )

    assert result.is_error is True
    assert client.invocations == []


@pytest.mark.anyio
async def test_executor_turn_on_rejects_unsupported_feature():
    client = FakeHomeAssistantClient()
    device = Device(
        id="light.temp_only",
        name="Lampa temp-only",
        kind="light",
        capabilities={**_CORE_CAPS, "turn_on": frozenset({"color_temp"})},
    )
    device_registry = DeviceRegistry([device])
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute("turn_on", {"entity_id": "light.temp_only", "rgb_color": [255, 0, 0]})

    assert result.is_error is True
    assert client.invocations == []


@pytest.mark.anyio
async def test_executor_turn_on_accepts_plain_call_without_light_params():
    client = FakeHomeAssistantClient()
    device = Device(
        id="light.rgb",
        name="Lampa RGB",
        kind="light",
        capabilities={**_CORE_CAPS, "turn_on": frozenset({"rgb", "color_temp"})},
    )
    device_registry = DeviceRegistry([device])
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute("turn_on", {"entity_id": "light.rgb"})

    assert result.is_error is False
    assert client.invocations == [("light.rgb", "turn_on")]


@pytest.mark.anyio
async def test_executor_turn_on_accepts_supported_combination_of_light_params():
    client = FakeHomeAssistantClient()
    device = Device(
        id="light.rgb",
        name="Lampa RGB",
        kind="light",
        capabilities={**_CORE_CAPS, "turn_on": frozenset({"brightness", "rgb"})},
    )
    device_registry = DeviceRegistry([device])
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute(
        "turn_on", {"entity_id": "light.rgb", "brightness_pct": 50, "rgb_color": [255, 0, 0]}
    )

    assert result.is_error is False
    assert client.invocations == [("light.rgb", "turn_on")]


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
    async def dispatch(name: str, arguments: dict[str, Any]) -> ToolResult:
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
# BasicToolsExtension — symetria Fakt<->narzędzie
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_basic_tools_get_time_dispatch_matches_fact_value_from_same_build():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension = BasicToolsExtension(data_dir=Path(tmp_dir) / "basic_tools")

        contribution = await extension.build(facts=[])
        result = await contribution.dispatch("get_time", {})

        assert len(contribution.facts) == 1
        assert contribution.facts[0].key == "aktualna_data_i_godzina"
        assert result.is_error is False
        assert result.content == contribution.facts[0].value


@pytest.mark.anyio
async def test_basic_tools_disabled_returns_empty_contribution():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension = BasicToolsExtension(data_dir=Path(tmp_dir) / "basic_tools")
        await extension.set_enabled(False)

        contribution = await extension.build(facts=[])

        assert contribution.tools == []
        assert contribution.entities == []
        assert contribution.facts == []


def test_basic_tools_build_router_mounts_without_error():
    extension = BasicToolsExtension()
    router = extension.build_router()
    assert isinstance(router, APIRouter)


# --------------------------------------------------------------------------
# Pełna pętla agentyczna (ReAct) w AgentEngine — Gateway + HomeAssistantExtension
# end-to-end, bez śladu rozszerzenia w odpowiedzi, adresowanie po opaque entity_id
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


async def _setup_home_assistant_extension(
    tmp_dir: str, declared: dict[str, str | None] | None = None
) -> tuple[HomeAssistantExtension, list[FakeHomeAssistantClient]]:
    """Wstrzykuje `FakeHomeAssistantClient` przez `client_factory`, konfiguruje singleton i deklaruje urządzenia.

    :param declared: Mapa entity_id -> display_name do zadeklarowania. `None`
        (domyślnie) deklaruje wszystkie urządzenia z `_make_raw_devices()` bez
        nadpisania nazwy — wygodny domyślny stan dla testów, którym opt-in nie
        jest przedmiotem badania.
    """
    created: list[FakeHomeAssistantClient] = []

    def factory(config: HomeAssistantConfig) -> FakeHomeAssistantClient:
        client = FakeHomeAssistantClient(devices=_make_raw_devices())
        created.append(client)
        return client

    extension = HomeAssistantExtension(data_dir=Path(tmp_dir) / "home_assistant", client_factory=factory)
    await extension.save_config(base_url="http://fake", access_token="secret")

    to_declare = declared if declared is not None else {d.id: None for d in _make_raw_devices()}
    for entity_id, display_name in to_declare.items():
        await extension.add_declared_device(entity_id=entity_id, display_name=display_name)

    return extension, created


@pytest.mark.anyio
async def test_agent_engine_react_loop_turns_on_single_device_via_opaque_entity_id():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension, created_clients = await _setup_home_assistant_extension(tmp_dir)
        gateway = Gateway(plugins=[extension])

        # Odkrywamy opaque ID encji "Światło w łazience" tak, jak zrobiłby to agent
        # na podstawie kanału Encji w kontekście (osobne wywołanie build() — dowód
        # na deterministyczną stabilność opaque ID między turami).
        discovery_build = await gateway.build()
        target_entity = next(e for e in discovery_build.entities if e.name == "Światło w łazience")

        llm_provider = ToolCallingMockProvider(tool_name="turn_on", entity_id=target_entity.id)
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=llm_provider, memory_manager=memory_manager, gateway=gateway)

        stream_events = [event async for event in engine.interact_stream(session_id="s1", prompt="Włącz światło w łazience")]

        client = created_clients[-1]
        assert client.invocations == [("light.bathroom", "turn_on")]
        assert len(llm_provider.calls_seen) == 2
        second_turn_messages = llm_provider.calls_seen[1]
        assert any(m.role == "tool" and "turn_on wykonane" in m.content for m in second_turn_messages)

        chunks = [event.payload["chunk"] for event in stream_events if event.type == "chunk"]
        assert "".join(chunks) == "Włączyłem światło."

        tool_start_events = [event for event in stream_events if event.type == "tool_start"]
        tool_result_events = [event for event in stream_events if event.type == "tool_result"]
        assert len(tool_start_events) == 1
        assert tool_start_events[0].payload["name"] == "turn_on"
        assert len(tool_result_events) == 1
        assert tool_result_events[0].payload["is_error"] is False
        assert "turn_on wykonane" in tool_result_events[0].payload["content"]

        history = memory_manager.get_history(session_id="s1")
        assert history[-1].role == "assistant"
        assert history[-1].content == "Włączyłem światło."
        persisted_steps = history[-1].metadata["steps"]
        assert [step["type"] for step in persisted_steps] == ["tool_call", "tool_result"]


@pytest.mark.anyio
async def test_agent_engine_react_loop_turns_on_group_with_partial_success_report():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension, created_clients = await _setup_home_assistant_extension(tmp_dir)
        await extension.create_group(
            name="Łazienka",
            device_ids=["light.bathroom", "light.bathroom_mirror"],
            custom_id="grp_bathroom",
        )
        gateway = Gateway(plugins=[extension])

        discovery_build = await gateway.build()
        group_entity = next(e for e in discovery_build.entities if e.name == "Łazienka")

        llm_provider = ToolCallingMockProvider(tool_name="turn_on", entity_id=group_entity.id)
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=llm_provider, memory_manager=memory_manager, gateway=gateway)

        _ = [chunk async for chunk in engine.interact_stream(session_id="s1", prompt="Włącz światła w łazience")]

        second_turn_messages = llm_provider.calls_seen[1]
        tool_result_message = next(m for m in second_turn_messages if m.role == "tool")
        assert "2/2" in tool_result_message.content


# --------------------------------------------------------------------------
# Katalog opt-in — tylko zadeklarowane urządzenia widoczne w build()
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_build_only_includes_declared_devices():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension, _ = await _setup_home_assistant_extension(tmp_dir, declared={"light.bathroom": None})

        contribution = await extension.build(facts=[])

        names = {e.name for e in contribution.entities}
        assert "Światło w łazience" in names
        assert "Światło w łazience — lustro" not in names


@pytest.mark.anyio
async def test_build_applies_display_name_override_from_declaration():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension, _ = await _setup_home_assistant_extension(
            tmp_dir, declared={"light.bathroom": "Lampka łazienkowa"}
        )

        contribution = await extension.build(facts=[])

        names = {e.name for e in contribution.entities}
        assert "Lampka łazienkowa" in names
        assert "Światło w łazience" not in names


@pytest.mark.anyio
async def test_build_with_no_declared_devices_shows_nothing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension, _ = await _setup_home_assistant_extension(tmp_dir, declared={})

        contribution = await extension.build(facts=[])

        assert contribution.entities == []


# --------------------------------------------------------------------------
# Przełącznik enabled całego rozszerzenia — Home Assistant i Basic Tools
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_home_assistant_build_returns_empty_contribution_when_disabled():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension, _ = await _setup_home_assistant_extension(tmp_dir)
        await extension.set_enabled(False)

        contribution = await extension.build(facts=[])

        assert contribution.tools == []
        assert contribution.entities == []


@pytest.mark.anyio
async def test_extension_state_defaults_to_enabled_true_without_state_file():
    with tempfile.TemporaryDirectory() as tmp_dir:
        extension = HomeAssistantExtension(data_dir=Path(tmp_dir) / "home_assistant")
        assert await extension.is_enabled() is True


# --------------------------------------------------------------------------
# Generyczny rejestr rozszerzeń — lista + przełącznik przez REST
# --------------------------------------------------------------------------


class _FakeNetworkExtension:
    """`NetworkExtension` testowy z trywialnym, w pełni izolowanym stanem enabled."""

    def __init__(self, extension_id: str, label: str, enabled: bool = True) -> None:
        self.extension_id = extension_id
        self.label = label
        self._enabled = enabled
        self.router_hits = 0

    async def is_enabled(self) -> bool:
        return self._enabled

    async def set_enabled(self, value: bool) -> None:
        self._enabled = value

    def build_router(self) -> APIRouter:
        router = APIRouter()

        @router.get("/ping")
        async def ping():
            self.router_hits += 1
            return {"pong": True}

        return router


def test_extensions_registry_router_lists_and_toggles_extensions():
    first = _FakeNetworkExtension("ext_a", "Rozszerzenie A", enabled=True)
    second = _FakeNetworkExtension("ext_b", "Rozszerzenie B", enabled=False)
    router = create_extensions_registry_router([first, second])

    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/api/v1/extensions")
        assert response.status_code == 200
        body = response.json()
        assert {(e["id"], e["enabled"]) for e in body["extensions"]} == {("ext_a", True), ("ext_b", False)}

        response = client.put("/api/v1/extensions/ext_b", json={"enabled": True})
        assert response.status_code == 200
        assert response.json()["enabled"] is True

        response = client.put("/api/v1/extensions/unknown", json={"enabled": True})
        assert response.status_code == 404


def test_network_gateway_mounts_extension_router_under_its_prefix():
    extension = _FakeNetworkExtension("ext_a", "Rozszerzenie A")

    # `agent_engine`/`backend_registry`/`prompt_store` są tu wyłącznie domykane
    # przez pod-routery jako referencje (dereferencjonowane dopiero przy
    # trafieniu w ich endpoint) — ten test wywołuje wyłącznie endpoint rozszerzenia.
    app = create_gateway_app(
        agent_engine=None,  # type: ignore[arg-type]
        backend_registry=None,  # type: ignore[arg-type]
        prompt_store=None,  # type: ignore[arg-type]
        extensions=[extension],
    )

    with TestClient(app) as client:
        response = client.get("/api/v1/extensions/ext_a/ping")
        assert response.status_code == 200
        assert response.json() == {"pong": True}
