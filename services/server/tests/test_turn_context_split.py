"""Podział promptu tury: co stabilne idzie na pozycję zerową, co zmienne — tuż
przed pytanie użytkownika.

Sedno tych testów to `test_system_message_is_byte_identical_across_turns`:
wcześniej wiadomość zerowa zawierała znacznik czasu, więc każda tura wyglądała
dla dostawcy jak zupełnie nowe żądanie. Reszta pilnuje, żeby fakty lądowały w
dokładnie właściwym miejscu, a brak faktów niczego nie zmieniał.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from shared import ChatMessageDTO

from server.agent.context.builder import ContextBuilder
from server.world.engine import WorldEngine
from server.world.models import ClientCapability, SenderProfile
from server.world.prompt_sections import PromptSectionsConfig, resolve_section

IDENTITY = "Jesteś Regis."


def _history(*pairs: tuple[str, str]) -> list[ChatMessageDTO]:
    return [
        ChatMessageDTO(role=role, content=content, timestamp=0.0)
        for role, content in pairs
    ]


def test_turn_context_lands_directly_before_last_user_message() -> None:
    builder = ContextBuilder()

    messages = builder.build_messages(
        session_history=_history(("user", "cześć"), ("assistant", "hej"), ("user", "zapal światło")),
        system_prompt=IDENTITY,
        turn_context="FAKTY",
    )

    roles_and_content = [(m.role, m.content) for m in messages]
    assert roles_and_content == [
        ("system", IDENTITY),
        ("user", "cześć"),
        ("assistant", "hej"),
        ("system", "FAKTY"),
        ("user", "zapal światło"),
    ]


def test_without_turn_context_layout_is_unchanged() -> None:
    """Regresja: brak faktów nie może zmienić niczego w układzie wiadomości."""
    builder = ContextBuilder()
    history = _history(("user", "cześć"), ("assistant", "hej"))

    messages = builder.build_messages(session_history=history, system_prompt=IDENTITY)

    assert [(m.role, m.content) for m in messages] == [
        ("system", IDENTITY),
        ("user", "cześć"),
        ("assistant", "hej"),
    ]


def test_turn_context_with_empty_history_is_appended() -> None:
    """Pierwsza tura sesji: nie ma przed czym wstawiać, więc fakty idą na koniec."""
    builder = ContextBuilder()

    messages = builder.build_messages(session_history=[], system_prompt=IDENTITY, turn_context="FAKTY")

    assert [(m.role, m.content) for m in messages] == [("system", IDENTITY), ("system", "FAKTY")]


def test_turn_context_precedes_prompt_passed_via_new_prompt() -> None:
    """Druga ścieżka `build_messages` — pytanie podane parametrem, nie z historii."""
    builder = ContextBuilder()

    messages = builder.build_messages(
        session_history=_history(("user", "cześć"), ("assistant", "hej")),
        new_prompt="zapal światło",
        system_prompt=IDENTITY,
        turn_context="FAKTY",
    )

    assert [(m.role, m.content) for m in messages][-2:] == [("system", "FAKTY"), ("user", "zapal światło")]


@pytest.mark.anyio
async def test_system_message_is_byte_identical_across_turns() -> None:
    """Sedno podziału: wiadomość zerowa nie może się zmienić między turami.

    Wcześniej zawierała znacznik czasu z `datetime.now()`, więc różniła się przy
    każdym wywołaniu i prefiks żądania nigdy się nie powtarzał.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        await engine.create_prompt(name="Tożsamość", content=IDENTITY, set_active=True)
        await engine.register_sender(
            "sat_1", SenderProfile(capabilities=frozenset({ClientCapability.SPEAKER}))
        )
        builder = ContextBuilder()

        system_messages: list[str] = []
        turn_contexts: list[str] = []
        for _ in range(2):
            build = await engine.build(sender_id="sat_1")
            messages = builder.build_messages(
                session_history=_history(("user", "cześć")),
                system_prompt=build.system_prompt,
                turn_context=build.turn_context,
            )
            system_messages.append(messages[0].content)
            turn_contexts.append(build.turn_context or "")

        assert system_messages[0] == system_messages[1]
        assert IDENTITY in system_messages[0]
        # Kontrola negatywna: fakty NADAL muszą nieść znacznik czasu — inaczej test
        # wyżej przechodziłby też wtedy, gdyby czas po prostu zniknął z promptu.
        assert "Aktualna data i godzina" in turn_contexts[0]


@pytest.mark.anyio
async def test_identity_stays_out_of_turn_context() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        engine = WorldEngine(data_dir=Path(tmp_dir) / "world")
        await engine.create_prompt(name="Tożsamość", content=IDENTITY, set_active=True)

        build = await engine.build()

        assert build.system_prompt == IDENTITY
        assert IDENTITY not in (build.turn_context or "")


# --------------------------------------------------------------------------
# Sekcje — nadpisanie / wyciszenie / domyślna / odporność na nawiasy klamrowe
# --------------------------------------------------------------------------


def test_section_falls_back_to_default_when_not_overridden() -> None:
    rendered = resolve_section(PromptSectionsConfig(), "delivery_text")
    assert rendered is not None and "tekst" in rendered


def test_section_override_replaces_default() -> None:
    config = PromptSectionsConfig(delivery_voice="MÓW KRÓTKO")
    assert resolve_section(config, "delivery_voice") == "MÓW KRÓTKO"


def test_empty_section_is_silenced_not_defaulted() -> None:
    """Wyczyszczenie pola to świadoma decyzja użytkownika ("nie chcę tego w
    prompcie"), a NIE to samo co przywrócenie wartości domyślnej."""
    config = PromptSectionsConfig(datetime="")
    assert resolve_section(config, "datetime", {"{czas}": "12:00"}) is None


def test_braces_in_user_text_do_not_break_substitution() -> None:
    """`str.format` wysypałby się tu `KeyError` — dlatego podstawiamy `str.replace`.
    Ludzie wklejają do promptów przykłady JSON i nie mogą tym wywalić każdej tury."""
    config = PromptSectionsConfig(location='Pokój: {pokój}. Przykład: {"a": 1} oraz {nieznane}.')

    rendered = resolve_section(config, "location", {"{pokój}": "Salon"})

    assert rendered == 'Pokój: Salon. Przykład: {"a": 1} oraz {nieznane}.'
