"""Testy modułów wydzielonych z `WorldEngine.build()` — `world/tools/` i `world/turn_context.py`.

Sens tego pliku jest strukturalny: przed wydzieleniem żadnej z tych rzeczy nie dało
się sprawdzić bez zbudowania całego silnika (z katalogiem danych, magazynami i
klientem Home Assistant). Teraz to czyste funkcje i mały obiekt routujący.
"""

from __future__ import annotations

import pytest
from server.ports.llm import ToolDefinition, ToolResult
from server.world.models import ClientCapability, Device, DeviceGroup, RoomInstanceConfig, SenderProfile
from server.world.prompt_sections import PromptSection, PromptSectionsConfig, TurnFacts
from server.world.tools import Tool, ToolSet, build_tool_definitions, get_time_tool, speak_in_room_tool
from server.world.turn_context import (
    build_turn_facts,
    format_capabilities,
    render_devices_section,
    render_turn_context,
    sections_gained_after_redirect,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _device(entity_id: str, name: str, room_id: str | None = None, **caps: frozenset[str]) -> Device:
    return Device(
        id=entity_id,
        name=name,
        kind="light",
        capabilities=caps or {"get_state": frozenset()},
        area=None,
        room_id=room_id,
    )


# --------------------------------------------------------------------------
# ToolSet — routing wywołań
# --------------------------------------------------------------------------


class _RecordingExecutor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def execute(self, tool_name: str, arguments: dict) -> ToolResult:
        self.calls.append(tool_name)
        return ToolResult(content=f"wykonano {tool_name}")


@pytest.mark.anyio
async def test_toolset_routes_to_own_tool():
    tools = ToolSet([get_time_tool("2026-08-24 12:00:00")])
    result = await tools.dispatch("get_time", {})
    assert result.content == "2026-08-24 12:00:00"
    assert not result.is_error


@pytest.mark.anyio
async def test_toolset_routes_declared_device_tools_to_executor():
    executor = _RecordingExecutor()
    tools = ToolSet([get_time_tool("teraz")])
    tools.add_home_assistant(executor, build_tool_definitions())

    result = await tools.dispatch("turn_on", {"entity_id": "light.x"})

    assert executor.calls == ["turn_on"]
    assert result.content == "wykonano turn_on"


@pytest.mark.anyio
async def test_toolset_rejects_unknown_name_instead_of_passing_it_to_executor():
    """Regresja: halucynowana nazwa narzędzia trafiała wcześniej do egzekutora Home
    Assistant, który odpowiadał "Nie znaleziono żadnej pasującej encji" — czyli kierował
    model na poprawianie `entity_id` zamiast powiedzieć, że takiego narzędzia nie ma."""
    executor = _RecordingExecutor()
    tools = ToolSet([get_time_tool("teraz")])
    tools.add_home_assistant(executor, build_tool_definitions())

    result = await tools.dispatch("wlacz_swiatlo_w_kuchni", {})

    assert executor.calls == []
    assert result.is_error
    assert "Nieznane narzędzie" in result.content


@pytest.mark.anyio
async def test_toolset_reports_unavailable_device_tools_without_client():
    """Urządzenia zadeklarowane, ale klient HA nie powstał — wywołanie musi wrócić
    błędem, nie wyjątkiem wywracającym całą turę."""
    tools = ToolSet([])
    tools.add_home_assistant(None, build_tool_definitions())

    result = await tools.dispatch("turn_off", {"entity_id": "light.x"})

    assert result.is_error
    assert "niedostępne" in result.content


@pytest.mark.anyio
async def test_toolset_converts_executor_exception_to_error_result():
    class _Exploding:
        async def execute(self, tool_name: str, arguments: dict) -> ToolResult:
            raise RuntimeError("timeout żarówki")

    tools = ToolSet([])
    tools.add_home_assistant(_Exploding(), build_tool_definitions())

    result = await tools.dispatch("turn_on", {"entity_id": "light.x"})

    assert result.is_error
    assert "timeout żarówki" in result.content


@pytest.mark.anyio
async def test_toolset_definitions_keep_builtin_tools_before_devices():
    tools = ToolSet([get_time_tool("teraz")])
    tools.add_home_assistant(_RecordingExecutor(), build_tool_definitions())

    names = [d.name for d in tools.definitions]

    assert names[0] == "get_time"
    assert set(names[1:]) == {"get_state", "turn_on", "turn_off"}


@pytest.mark.anyio
async def test_custom_tool_needs_no_change_in_toolset():
    """Dowód, że dodanie narzędzia nie wymaga już operacji w środku budowania promptu."""

    async def handler(arguments: dict) -> ToolResult:
        return ToolResult(content=f"echo: {arguments['tekst']}")

    tool = Tool(
        definition=ToolDefinition(name="echo", description="", parameters={"type": "object", "properties": {}}),
        handler=handler,
    )
    result = await ToolSet([tool]).dispatch("echo", {"tekst": "test"})
    assert result.content == "echo: test"


# --------------------------------------------------------------------------
# speak_in_room — wstrzyknięte zależności zamiast wiedzy o rejestrach
# --------------------------------------------------------------------------


def _facts(**overrides) -> TurnFacts:
    base = dict(
        now="2026-08-24 12:00:00",
        date="2026-08-24",
        clock="12:00",
        weekday="poniedziałek",
        capabilities=frozenset({"text"}),
        room_id=None,
        room_name=None,
        client_name=None,
        device_list=None,
        room_device_list=None,
    )
    base.update(overrides)
    return TurnFacts(**base)


@pytest.mark.anyio
async def test_speak_in_room_errors_when_no_speaker_in_room():
    async def find_speaker(room: str):
        return None, []

    async def describe(sender_id: str):
        return None, None

    tool = speak_in_room_tool(find_speaker, describe, PromptSectionsConfig(sections=[]), _facts())
    result = await tool.handler({"room": "Kuchnia"})

    assert result.is_error
    assert result.redirect_sender_id is None
    assert "Brak odbiornika z głośnikiem" in result.content


@pytest.mark.anyio
async def test_speak_in_room_errors_on_ambiguous_room():
    async def find_speaker(room: str):
        return None, ["snd_a", "snd_b"]

    async def describe(sender_id: str):
        return None, None

    tool = speak_in_room_tool(find_speaker, describe, PromptSectionsConfig(sections=[]), _facts())
    result = await tool.handler({"room": "Salon"})

    assert result.is_error
    assert "wielu odbiorników" in result.content


@pytest.mark.anyio
async def test_speak_in_room_redirects_and_adds_only_newly_valid_sections():
    """Model dostaje RÓŻNICĘ kontekstu, nie cały kontekst od nowa — inaczej lista
    urządzeń wracałaby do niego po raz drugi w tej samej turze."""
    target = SenderProfile(
        display_name="Głośnik kuchenny", room_id="room_k", capabilities=frozenset({ClientCapability.SPEAKER})
    )

    async def find_speaker(room: str):
        return "snd_kuchnia", []

    async def describe(sender_id: str):
        return target, "Kuchnia"

    sections = PromptSectionsConfig(
        sections=[
            PromptSection(
                id="s1", label="Dostawa", condition="client_has_speaker",
                text="Odpowiedź zostanie odczytana na głos.", text_negated="Odpowiedź zostanie wyświetlona.",
            ),
            PromptSection(id="s2", label="Czas", condition="always", text="Jest {godzina}.", text_negated=""),
        ]
    )
    tool = speak_in_room_tool(find_speaker, describe, sections, _facts())
    result = await tool.handler({"room": "Kuchnia"})

    assert result.redirect_sender_id == "snd_kuchnia"
    assert "Przełączono dalszą odpowiedź na pokój 'Kuchnia'." in result.content
    # sekcja dostawy zmieniła gałąź -> dokładana; sekcja czasu jest niezmieniona -> pomijana
    assert "odczytana na głos" in result.content
    assert "Jest 12:00" not in result.content


# --------------------------------------------------------------------------
# turn_context — czyste renderowanie, zero I/O
# --------------------------------------------------------------------------


def test_format_capabilities_sorts_tools_and_features():
    device = _device("light.a", "Lampa", turn_on=frozenset({"rgb", "brightness"}), get_state=frozenset())
    assert format_capabilities(device) == "get_state, turn_on[brightness, rgb]"


def test_format_capabilities_of_device_without_any():
    assert format_capabilities(Device(id="x", name="X", kind="", capabilities={}, area=None)) == "brak"


def test_devices_section_puts_current_room_first_and_marks_it():
    rooms = {"r1": RoomInstanceConfig(id="r1", name="Salon"), "r2": RoomInstanceConfig(id="r2", name="Kuchnia")}
    devices = [_device("light.k", "Lampa kuchenna", "r2"), _device("light.s", "Lampa salonowa", "r1")]

    rendered = render_devices_section(devices, [], rooms_by_id=rooms, current_room_id="r1")

    assert rendered.index("### Salon (Twoja lokalizacja)") < rendered.index("### Kuchnia")


def test_devices_section_treats_unknown_room_as_unassigned():
    """Usunięcie pokoju nie kasuje przypisań urządzeń (brak cascade delete) — urządzenie
    wskazujące na nieistniejący `room_id` musi zostać widoczne, nie zniknąć."""
    devices = [_device("light.x", "Sierota", "room_usuniety")]

    rendered = render_devices_section(devices, [], rooms_by_id={}, current_room_id=None)

    assert "### (bez przypisanego pokoju)" in rendered
    assert "[light.x] Sierota" in rendered


def test_devices_section_lists_groups_with_device_tool_names():
    groups = [DeviceGroup(id="grp_1", name="Wszystkie światła", device_ids=["light.x"])]

    rendered = render_devices_section([], groups, rooms_by_id={}, current_room_id=None)

    assert "### Grupy" in rendered
    assert "[grp_1] Wszystkie światła (możliwości: get_state, turn_on, turn_off)" in rendered


def test_turn_facts_derive_modality_from_client_capabilities():
    """Modalność to trwały fakt o kliencie, nie flaga wywołania (dawne `voice_mode`)."""
    profile = SenderProfile(display_name="Satelita", room_id="r1", capabilities=frozenset({ClientCapability.SPEAKER}))
    room = RoomInstanceConfig(id="r1", name="Salon")

    facts = build_turn_facts(
        now=__import__("datetime").datetime(2026, 8, 24, 12, 0, 0),
        profile=profile,
        current_room=room,
        rooms_by_id={"r1": room},
        devices=[_device("light.s", "Lampa", "r1")],
        groups=[],
        ha_configured=True,
    )

    assert facts.capabilities == frozenset({"speaker"})
    assert facts.weekday == "poniedziałek"
    assert facts.room_name == "Salon"
    assert facts.client_name == "Satelita"
    assert facts.room_device_list is not None and "[light.s] Lampa" in facts.room_device_list


def test_render_turn_context_returns_none_when_nothing_applies():
    sections = PromptSectionsConfig(
        sections=[PromptSection(id="s", label="", condition="has_devices", text="Urządzenia: {lista_urządzeń}", text_negated="")]
    )
    assert render_turn_context(sections, _facts(device_list=None)) is None


def test_sections_gained_after_redirect_skips_unchanged_sections():
    sections = PromptSectionsConfig(
        sections=[PromptSection(id="s", label="", condition="always", text="Zawsze to samo.", text_negated="")]
    )
    target = SenderProfile(display_name=None, room_id="r1", capabilities=frozenset({ClientCapability.SPEAKER}))

    assert sections_gained_after_redirect(sections, _facts(), target, "Salon") == []
