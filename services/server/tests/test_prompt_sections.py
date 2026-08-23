"""Komponowalne sekcje kontekstu tury: warunki, dwie gałęzie tekstu, kolejność, migracja.

Warunki są czystymi funkcjami `TurnFacts -> bool`, więc testują się bez żadnego
I/O — o to chodziło w wydzieleniu `TurnFacts` z `WorldEngine.build()`.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from server.world.prompt_sections import (
    PLACEHOLDER_DEVICES,
    PLACEHOLDER_ROOM,
    PLACEHOLDER_TIME,
    PromptSection,
    PromptSectionsConfig,
    PromptSectionStore,
    TurnFacts,
    default_sections,
    render_section,
    section_condition_holds,
    section_warnings,
)


def _facts(**overrides) -> TurnFacts:
    base = {
        "now": "2026-08-22 12:00:00",
        "date": "2026-08-22",
        "clock": "12:00",
        "weekday": "sobota",
        "capabilities": frozenset(),
        "room_id": None,
        "room_name": None,
        "client_name": None,
        "device_list": None,
        "room_device_list": None,
        "ha_configured": False,
    }
    base.update(overrides)
    return TurnFacts(**base)


# --------------------------------------------------------------------------
# Warunki
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "condition,facts,expected",
    [
        ("always", _facts(), True),
        ("client_has_speaker", _facts(capabilities=frozenset({"speaker"})), True),
        ("client_has_speaker", _facts(capabilities=frozenset({"text"})), False),
        ("client_has_mic", _facts(capabilities=frozenset({"mic"})), True),
        ("client_has_mic", _facts(), False),
        ("client_has_room", _facts(room_id="room_1"), True),
        ("client_has_room", _facts(), False),
        ("has_devices", _facts(device_list="- [light.a] Lampa"), True),
        ("has_devices", _facts(), False),
        ("ha_configured", _facts(ha_configured=True), True),
        ("ha_configured", _facts(), False),
    ],
)
def test_condition_predicates(condition: str, facts: TurnFacts, expected: bool) -> None:
    assert section_condition_holds(PromptSection(text="x", condition=condition), facts) is expected


def test_condition_with_param_matches_only_that_room() -> None:
    section = PromptSection(text="x", condition="client_in_room", condition_param="room_salon")
    assert section_condition_holds(section, _facts(room_id="room_salon")) is True
    assert section_condition_holds(section, _facts(room_id="room_kuchnia")) is False
    assert section_condition_holds(section, _facts()) is False


def test_two_branches_replace_the_pair_of_negated_sections() -> None:
    """Sedno zmiany: jedna decyzja ("czy klient ma głośnik?") to JEDEN wpis listy z dwoma
    tekstami — wcześniej były to dwie sekcje, które nic formalnie nie łączyło i które dało
    się niezależnie przestawić w odległe miejsca promptu."""
    section = PromptSection(
        text="mówię na głos", text_negated="piszę tekstem", condition="client_has_speaker"
    )

    assert render_section(section, _facts(capabilities=frozenset({"speaker"}))) == "mówię na głos"
    assert render_section(section, _facts(capabilities=frozenset({"text"}))) == "piszę tekstem"


def test_empty_branch_means_say_nothing_not_error() -> None:
    """Pusta gałąź to poprawny, częsty stan — "gdy warunek niespełniony nie mów nic"."""
    section = PromptSection(text="tylko z głośnikiem", text_negated="", condition="client_has_speaker")

    assert render_section(section, _facts()) is None


def test_unknown_condition_skips_section_instead_of_crashing() -> None:
    """Nieznany warunek (np. plik zapisany przez nowszą wersję) nie może wywalić
    tury — sekcja po prostu nie wchodzi do promptu, ŻADNĄ gałęzią."""
    section = PromptSection(text="a", text_negated="b", condition="nie_istnieje")
    assert section_condition_holds(section, _facts()) is None
    assert render_section(section, _facts()) is None


# --------------------------------------------------------------------------
# Renderowanie
# --------------------------------------------------------------------------


def test_render_substitutes_all_placeholders() -> None:
    section = PromptSection(
        text=f"{PLACEHOLDER_TIME} / {PLACEHOLDER_ROOM} / {PLACEHOLDER_DEVICES}",
        condition="always",
    )
    facts = _facts(room_name="Salon", device_list="- [light.a] Lampa")

    assert render_section(section, facts) == "2026-08-22 12:00:00 / Salon / - [light.a] Lampa"


def test_render_returns_none_for_empty_text() -> None:
    assert render_section(PromptSection(text="", condition="always"), _facts()) is None


def test_braces_in_user_text_do_not_break_substitution() -> None:
    """`str.format` wysypałby się tu `KeyError` — dlatego podstawiamy `str.replace`.
    Ludzie wklejają do promptów przykłady JSON i nie mogą tym wywalić każdej tury."""
    section = PromptSection(
        text=f'Pokój: {PLACEHOLDER_ROOM}. Przykład: {{"a": 1}} oraz {{nieznane}}.',
        condition="always",
    )

    rendered = render_section(section, _facts(room_name="Salon"))

    assert rendered == 'Pokój: Salon. Przykład: {"a": 1} oraz {nieznane}.'


# --------------------------------------------------------------------------
# Ostrzeżenia — informują, nie blokują
# --------------------------------------------------------------------------


def test_warns_when_placeholder_used_in_negated_branch() -> None:
    """Gałąź "gdy NIE spełniony" z definicji działa wtedy, gdy warunek nie zachodzi —
    więc żadna gwarancja warunku jej nie obejmuje."""
    section = PromptSection(text="ok", text_negated=f"Pokój: {PLACEHOLDER_ROOM}", condition="client_has_room")
    assert any(PLACEHOLDER_ROOM in w for w in section_warnings(section))


def test_warns_when_placeholder_not_guaranteed_by_condition() -> None:
    section = PromptSection(text=f"Pokój: {PLACEHOLDER_ROOM}", condition="always")
    warnings = section_warnings(section)
    assert len(warnings) == 1 and PLACEHOLDER_ROOM in warnings[0]


def test_no_warning_when_condition_guarantees_placeholder() -> None:
    section = PromptSection(text=f"Pokój: {PLACEHOLDER_ROOM}", condition="client_has_room")
    assert section_warnings(section) == []


def test_warns_when_parametrised_condition_has_no_value() -> None:
    section = PromptSection(text="x", condition="client_in_room", condition_param=None)
    assert any("wymaga wybrania wartości" in w for w in section_warnings(section))


# --------------------------------------------------------------------------
# Kolejność i magazyn
# --------------------------------------------------------------------------


def test_section_order_is_prompt_order() -> None:
    facts = _facts()
    config = PromptSectionsConfig(
        sections=[
            PromptSection(text="drugi", condition="always"),
            PromptSection(text="pierwszy", condition="always"),
        ]
    )
    rendered = [render_section(s, facts) for s in config.sections]
    assert rendered == ["drugi", "pierwszy"]


@pytest.mark.anyio
async def test_store_seeds_defaults_on_first_load() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = PromptSectionStore(Path(tmp_dir))
        config = await store.load()
        assert [s.id for s in config.sections] == [s.id for s in default_sections()]


@pytest.mark.anyio
async def test_store_migrates_legacy_flat_format_preserving_overrides() -> None:
    """Pierwsza wersja modułu trzymała sześć nazwanych pól zamiast listy. Migracja
    nie może po cichu zgubić tekstu, który użytkownik zdążył wpisać."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "prompt_sections.json"
        path.write_text(
            json.dumps({"datetime": None, "delivery_voice": "MÓJ TEKST", "location": None, "extra": "DOPISEK"}),
            encoding="utf-8",
        )

        config = await PromptSectionStore(Path(tmp_dir)).load()

        by_id = {s.id: s for s in config.sections}
        assert by_id["sec_delivery"].text == "MÓJ TEKST"
        assert by_id["sec_datetime"].text == default_sections()[0].text  # brak nadpisania -> domyślna
        assert by_id["sec_extra"].text == "DOPISEK"
        # Migracja musi być trwała — kolejny odczyt nie może znowu widzieć starego kształtu.
        assert "sections" in json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.anyio
async def test_store_merges_negated_pair_into_one_two_branch_section() -> None:
    """Migracja z modelu "osobna sekcja z flagą negacji". Para o tym samym warunku, gdzie
    jedna jest zanegowana, opisuje JEDNĄ decyzję rozbitą na dwa wpisy — scalamy ją w jedną
    sekcję z dwiema gałęziami, zachowując etykietę i pozycję wpisu niezanegowanego."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "prompt_sections.json"
        path.write_text(
            json.dumps(
                {
                    "sections": [
                        {"id": "sec_a", "label": "Czas", "text": "teraz", "condition": "always"},
                        {
                            "id": "sec_voice",
                            "label": "Dostawa głosowa",
                            "text": "mówię",
                            "condition": "client_has_speaker",
                        },
                        {
                            "id": "sec_text",
                            "label": "Dostawa tekstowa",
                            "text": "piszę",
                            "condition": "client_has_speaker",
                            "negated": True,
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )

        config = await PromptSectionStore(Path(tmp_dir)).load()

        assert [s.id for s in config.sections] == ["sec_a", "sec_voice"]
        merged = config.sections[1]
        assert (merged.label, merged.text, merged.text_negated) == ("Dostawa głosowa", "mówię", "piszę")
        # Migracja musi być trwała — kolejny odczyt nie może znowu widzieć starego kształtu.
        assert not any(entry.get("negated") for entry in json.loads(path.read_text(encoding="utf-8"))["sections"])


@pytest.mark.anyio
async def test_negated_section_without_partner_keeps_its_own_entry() -> None:
    """Zanegowana sekcja bez pary nie ma z czym się scalić — zostaje osobnym wpisem
    z wypełnioną wyłącznie gałęzią "gdy NIE spełniony", czyli zachowuje się dokładnie
    tak jak przed migracją."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "prompt_sections.json"
        path.write_text(
            json.dumps(
                {"sections": [{"id": "sec_x", "label": "Bez HA", "text": "brak", "condition": "ha_configured", "negated": True}]}
            ),
            encoding="utf-8",
        )

        config = await PromptSectionStore(Path(tmp_dir)).load()

        assert len(config.sections) == 1
        assert (config.sections[0].text, config.sections[0].text_negated) == ("", "brak")


@pytest.mark.anyio
async def test_file_already_in_new_format_is_not_rewritten() -> None:
    """Brak czego migrować = brak zapisu. Bez tego każdy odczyt przepisywałby plik."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "prompt_sections.json"
        store = PromptSectionStore(Path(tmp_dir))
        await store.save(PromptSectionsConfig(sections=[PromptSection(text="a", condition="always")]))
        before = path.stat().st_mtime_ns

        await store.load()

        assert path.stat().st_mtime_ns == before


@pytest.mark.anyio
async def test_reset_restores_default_set() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = PromptSectionStore(Path(tmp_dir))
        await store.save(PromptSectionsConfig(sections=[PromptSection(text="własna", condition="always")]))

        restored = await store.reset()

        assert [s.id for s in restored.sections] == [s.id for s in default_sections()]
