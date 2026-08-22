import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, List

import pytest

from server.agent import AgentEngine
from server.agent.llm import BaseLLMProvider, LLMMessage, ToolCallRequest, ToolDefinition, ToolResult
from server.agent.context.builder import ContextBuilder
from server.agent.context_provider import NullWorldInterface
from server.agent.memory import MemoryManager
from server.world.client import HomeAssistantClient
from server.world.engine import WorldEngine
from server.world.models import ClientCapability, Device, DeviceGroup, HomeAssistantConfig, SenderProfile
from server.world.registry import DeviceRegistry
from server.world.tools import HomeAssistantToolExecutor


_CORE_CAPS = {"turn_on": frozenset(), "turn_off": frozenset(), "get_state": frozenset()}


def _make_devices() -> list[Device]:
    return [
        Device(id="light.bathroom", name="Światło w łazience", kind="light", capabilities=dict(_CORE_CAPS)),
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
    return DeviceGroup(id="grp_bathroom", name="Łazienka", device_ids=["light.bathroom", "light.bathroom_mirror"])


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
async def test_executor_group_aggregates_partial_failure():
    client = FakeHomeAssistantClient(failing_device_id="light.bathroom_mirror")
    device_registry = DeviceRegistry(_make_devices(), [_make_group()])
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute("turn_on", {"entity_id": "grp_bathroom"})

    assert result.is_error is False
    assert "1/2" in result.content


@pytest.mark.anyio
async def test_executor_array_entity_id_invokes_all_without_predefined_group():
    """Ad-hoc tablica entity_id — bez żadnej zapisanej grupy, model sam składa zestaw."""
    client = FakeHomeAssistantClient()
    device_registry = DeviceRegistry(_make_devices())
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute(
        "turn_off", {"entity_id": ["light.bathroom", "light.bathroom_mirror"]}
    )

    assert result.is_error is False
    assert "2/2" in result.content
    assert set(client.invocations) == {
        ("light.bathroom", "turn_off"),
        ("light.bathroom_mirror", "turn_off"),
    }


@pytest.mark.anyio
async def test_executor_array_mixes_device_and_group_ref():
    """Tablica może mieszać pojedyncze entity_id i group_id naraz — grupa się rozwija."""
    client = FakeHomeAssistantClient()
    kitchen = Device(id="light.kitchen", name="Kuchnia", kind="light", capabilities=dict(_CORE_CAPS))
    device_registry = DeviceRegistry(_make_devices() + [kitchen], [_make_group()])
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute("turn_off", {"entity_id": ["grp_bathroom", "light.kitchen"]})

    assert result.is_error is False
    assert "3/3" in result.content
    assert set(client.invocations) == {
        ("light.bathroom", "turn_off"),
        ("light.bathroom_mirror", "turn_off"),
        ("light.kitchen", "turn_off"),
    }


@pytest.mark.anyio
async def test_executor_array_with_unknown_entity_id_reports_partial_failure():
    client = FakeHomeAssistantClient()
    device_registry = DeviceRegistry(_make_devices())
    executor = HomeAssistantToolExecutor(device_registry, client)

    result = await executor.execute(
        "turn_off", {"entity_id": ["light.bathroom", "light.nieistniejace"]}
    )

    assert result.is_error is False
    assert "1/2" in result.content
    assert "nieznana encja" in result.content
    assert client.invocations == [("light.bathroom", "turn_off")]


def test_decode_light_infers_brightness_and_color_from_color_modes():
    from server.world.client import _decode_light

    caps = _decode_light({"supported_color_modes": ["color_temp", "hs", "rgb"], "supported_features": 44})

    assert set(caps) == {"turn_on", "turn_off", "get_state"}
    assert caps["turn_on"] == frozenset({"brightness", "color_temp", "hs", "rgb"})


# --------------------------------------------------------------------------
# WorldEngine.build() — pokój/capabilities niezależne od dostępności Home Assistant
# --------------------------------------------------------------------------


async def _engine_with_ha(
    tmp_dir: str,
    devices: list[Device],
    declared: dict[str, str | None] | None = None,
    room_ids: dict[str, str] | None = None,
):
    created: list[FakeHomeAssistantClient] = []

    def factory(config: HomeAssistantConfig) -> FakeHomeAssistantClient:
        client = FakeHomeAssistantClient(devices=devices)
        created.append(client)
        return client

    engine = WorldEngine(data_dir=Path(tmp_dir) / "world", client_factory=factory)
    await engine.save_config(base_url="http://fake", access_token="secret")
    to_declare = declared if declared is not None else {d.id: None for d in devices}
    room_ids = room_ids or {}
    for entity_id, display_name in to_declare.items():
        await engine.add_declared_device(entity_id=entity_id, display_name=display_name, room_id=room_ids.get(entity_id))
    return engine, created


@pytest.mark.anyio
async def test_build_without_config_still_returns_time_tool_and_no_error():
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")

        context_build = await engine.build()

        assert [t.name for t in context_build.tool_definitions] == ["get_time", "speak_in_room"]
        result = await context_build.dispatch("get_time", {})
        assert result.is_error is False


@pytest.mark.anyio
async def test_build_speaker_framing_and_room_survive_missing_ha_config():
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        room = await engine.create_room(name="Salon")
        await engine.register_sender(
            "sat_1", SenderProfile(room_id=room.id, capabilities=frozenset({ClientCapability.SPEAKER}))
        )

        context_build = await engine.build(sender_id="sat_1")

        assert "na głos" in context_build.turn_context
        assert "Salon" in context_build.turn_context
        # Brak konfiguracji HA nie dodaje narzędzi domowych, ale nie psuje frazowania.
        assert [t.name for t in context_build.tool_definitions] == ["get_time", "speak_in_room"]


@pytest.mark.anyio
async def test_build_unregistered_sender_id_has_no_room_framing():
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")

        context_build = await engine.build(sender_id="unknown_sender")

        assert "Nadawca" not in context_build.turn_context


@pytest.mark.anyio
async def test_build_speaker_framing_is_independent_of_room_registration():
    """Ramowanie dostawy zależy wyłącznie od `capabilities` klienta — przypisanie do
    pokoju jest osobną, opcjonalną informacją i jego brak nie może go wyłączyć."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        await engine.register_sender(
            "sat_no_room", SenderProfile(capabilities=frozenset({ClientCapability.SPEAKER}))
        )

        context_build = await engine.build(sender_id="sat_no_room")

        assert "na głos" in context_build.turn_context
        assert "Nadawca znajduje się" not in context_build.turn_context


@pytest.mark.anyio
async def test_build_text_client_gets_text_framing_not_voice():
    """Klient bez głośnika musi dostać ramowanie tekstowe — dawna flaga `voice_mode`
    opisywała wejście, a decydowała o wyjściu, przez co karta przeglądarki potrafiła
    dostać instrukcję "unikaj Markdown"."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        await engine.register_sender("web_1", SenderProfile(capabilities=frozenset({ClientCapability.TEXT})))

        context_build = await engine.build(sender_id="web_1")

        assert "wyświetlona jako tekst" in context_build.turn_context
        assert "na głos" not in context_build.turn_context


@pytest.mark.anyio
async def test_build_segregates_devices_by_room_and_marks_current_room():
    with tempfile.TemporaryDirectory() as tmp_dir:
        devices = [
            Device(id="light.salon", name="Lampa", kind="light", capabilities=dict(_CORE_CAPS), area="salon"),
            Device(id="light.kuchnia", name="Lampa2", kind="light", capabilities=dict(_CORE_CAPS), area="kuchnia"),
        ]
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        room_salon = await engine.create_room(name="Salon")
        room_kuchnia = await engine.create_room(name="Kuchnia")
        engine, _ = await _engine_with_ha(
            tmp_dir, devices, room_ids={"light.salon": room_salon.id, "light.kuchnia": room_kuchnia.id}
        )
        await engine.register_sender("sat_1", SenderProfile(room_id=room_salon.id))

        context_build = await engine.build(sender_id="sat_1")

        assert "### Salon (Twoja lokalizacja)" in context_build.turn_context
        assert "### Kuchnia" in context_build.turn_context
        assert "light.salon" in context_build.turn_context
        assert "light.kuchnia" in context_build.turn_context  # nadal w pełni widoczne, tylko posegregowane


@pytest.mark.anyio
async def test_build_segregates_unassigned_devices_when_room_missing():
    """Urządzenie bez `room_id` (albo wskazujące na usunięty pokój) trafia do
    sekcji "bez przypisanego pokoju" — bez cascade delete, bez błędu."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        devices = [Device(id="light.salon", name="Lampa", kind="light", capabilities=dict(_CORE_CAPS))]
        engine, _ = await _engine_with_ha(tmp_dir, devices)

        context_build = await engine.build()

        assert "### (bez przypisanego pokoju)" in context_build.turn_context
        assert "light.salon" in context_build.turn_context


@pytest.mark.anyio
async def test_build_dispatch_can_act_on_device_outside_current_room():
    with tempfile.TemporaryDirectory() as tmp_dir:
        devices = [
            Device(id="light.salon", name="Lampa", kind="light", capabilities=dict(_CORE_CAPS), area="salon"),
            Device(id="light.kuchnia", name="Lampa2", kind="light", capabilities=dict(_CORE_CAPS), area="kuchnia"),
        ]
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        room_salon = await engine.create_room(name="Salon")
        room_kuchnia = await engine.create_room(name="Kuchnia")
        engine, created = await _engine_with_ha(
            tmp_dir, devices, room_ids={"light.salon": room_salon.id, "light.kuchnia": room_kuchnia.id}
        )
        await engine.register_sender("sat_1", SenderProfile(room_id=room_salon.id))

        context_build = await engine.build(sender_id="sat_1")
        result = await context_build.dispatch("turn_on", {"entity_id": "light.kuchnia"})

        assert result.is_error is False
        assert created[-1].invocations == [("light.kuchnia", "turn_on")]


# --------------------------------------------------------------------------
# speak_in_room — rezolucja pokój -> sender_id, opaque redirect_sender_id
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_speak_in_room_resolves_room_to_sender_id():
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        room = await engine.create_room(name="Kuchnia")
        await engine.register_sender(
            "snd_kuchnia", SenderProfile(room_id=room.id, capabilities=frozenset({ClientCapability.SPEAKER}))
        )

        context_build = await engine.build()
        result = await context_build.dispatch("speak_in_room", {"room": "Kuchnia"})

        assert result.is_error is False
        assert result.redirect_sender_id == "snd_kuchnia"
        # Wynik niesie NOWE ramowanie dostawy — prompt systemowy powstał przed turą i
        # nie wie o przekierowaniu; pętla ReAct oddaje modelowi treść wyniku narzędzia.
        assert "na głos" in result.content


@pytest.mark.anyio
async def test_speak_in_room_skips_client_without_speaker():
    """Klient bez głośnika (np. karta przeglądarki przypisana do pokoju) nie jest
    kandydatem na odbiornik mowy — wcześniej przekierowanie przechodziło i odpowiedź
    znikała bez żadnego sygnału."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        room = await engine.create_room(name="Kuchnia")
        await engine.register_sender(
            "web_kuchnia", SenderProfile(room_id=room.id, capabilities=frozenset({ClientCapability.TEXT}))
        )

        context_build = await engine.build()
        result = await context_build.dispatch("speak_in_room", {"room": "Kuchnia"})

        assert result.is_error is True
        assert result.redirect_sender_id is None


@pytest.mark.anyio
async def test_speak_in_room_unknown_room_is_error_without_redirect():
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")

        context_build = await engine.build()
        result = await context_build.dispatch("speak_in_room", {"room": "Piwnica"})

        assert result.is_error is True
        assert result.redirect_sender_id is None


@pytest.mark.anyio
async def test_speak_in_room_ambiguous_room_is_error():
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        room = await engine.create_room(name="Salon")
        await engine.register_sender("snd_a", SenderProfile(room_id=room.id))
        await engine.register_sender("snd_b", SenderProfile(room_id=room.id))

        context_build = await engine.build()
        result = await context_build.dispatch("speak_in_room", {"room": "salon"})

        assert result.is_error is True
        assert result.redirect_sender_id is None


# --------------------------------------------------------------------------
# Room — CRUD i import z HA Areas (jednorazowy, nie live-sync)
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_room_crud_roundtrip():
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")

        created = await engine.create_room(name="Salon")
        assert (await engine.list_rooms())[created.id].name == "Salon"

        updated = await engine.update_room(room_id=created.id, name="Duży Salon")
        assert updated.name == "Duży Salon"

        assert await engine.delete_room(created.id) is True
        assert created.id not in await engine.list_rooms()


# --------------------------------------------------------------------------
# AgentEngine — NullWorldInterface domyślny, pętla ReAct z WorldEngine end-to-end
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_agent_engine_default_world_is_null_and_has_no_tools():
    class EchoProvider(BaseLLMProvider):
        def __init__(self) -> None:
            self._model = "echo"

        async def generate_stream(self, messages, tools=None, **kwargs) -> AsyncIterator[Any]:
            yield "ok"

        async def check_health(self) -> bool:
            return True

    with tempfile.TemporaryDirectory() as tmp_dir:
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        engine = AgentEngine(llm_provider=EchoProvider(), memory_manager=memory_manager)

        assert isinstance(engine.world, NullWorldInterface)
        _ = [chunk async for chunk in engine.interact_stream(session_id="s1", prompt="cześć")]

        history = memory_manager.get_history(session_id="s1")
        assert history[-1].content == "ok"


class ToolCallingMockProvider(BaseLLMProvider):
    """Pierwsza tura żąda wywołania narzędzia, druga zwraca finalną odpowiedź tekstową."""

    def __init__(self, tool_name: str, entity_id: str) -> None:
        self._model = "mock-tool-model"
        self._tool_name = tool_name
        self._entity_id = entity_id
        self.calls_seen: list[list[LLMMessage]] = []

    async def generate_stream(
        self, messages: List[LLMMessage], tools: list[ToolDefinition] | None = None, **kwargs: Any
    ) -> AsyncIterator[Any]:
        self.calls_seen.append(messages)
        if len(self.calls_seen) == 1:
            yield ToolCallRequest(id="call_1", name=self._tool_name, arguments={"entity_id": self._entity_id})
        else:
            yield "Włączyłem światło."

    async def check_health(self) -> bool:
        return True


@pytest.mark.anyio
async def test_agent_engine_react_loop_turns_on_device_via_world_engine():
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine, created_clients = await _engine_with_ha(tmp_dir, _make_devices())

        llm_provider = ToolCallingMockProvider(tool_name="turn_on", entity_id="light.bathroom")
        memory_manager = MemoryManager(data_dir=Path(tmp_dir) / "sessions")
        agent_engine = AgentEngine(llm_provider=llm_provider, memory_manager=memory_manager, world=engine)

        stream_events = [
            event async for event in agent_engine.interact_stream(session_id="s1", prompt="Włącz światło w łazience")
        ]

        client = created_clients[-1]
        assert client.invocations == [("light.bathroom", "turn_on")]
        chunks = [event.payload["chunk"] for event in stream_events if event.type == "chunk"]
        assert "".join(chunks) == "Włączyłem światło."
