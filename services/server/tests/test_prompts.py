"""Testy jednostkowe dla WorldPromptStore (CRUD, limit 3, fallback) i AgentDefaultPromptStore."""

import tempfile
from pathlib import Path

import pytest
from server.agent.context.builder import DEFAULT_SYSTEM_PROMPT
from server.agent.prompts import AgentDefaultPromptStore
from server.world.prompts import WorldPromptStore


def make_store(tmp_path: Path) -> WorldPromptStore:
    """Tworzy izolowaną instancję WorldPromptStore w tymczasowym katalogu."""
    return WorldPromptStore(tmp_path)


# ---------------------------------------------------------------------------
# Testy inicjalizacji i domyślnego profilu
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ensure_defaults_creates_empty_profile() -> None:
    """Przy pustym katalogu ensure_defaults() tworzy pusty profil "Profil 1"."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        prompts = await store.list_all()
        assert len(prompts) == 1
        assert prompts[0].id == "profile_1"
        assert prompts[0].content == ""


@pytest.mark.anyio
async def test_ensure_defaults_sets_active_id() -> None:
    """ensure_defaults() ustawia profile_1 jako aktywny."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        active_id = await store.get_active_id()
        assert active_id == "profile_1"


@pytest.mark.anyio
async def test_ensure_defaults_idempotent() -> None:
    """Wielokrotne wywołanie ensure_defaults() nie duplikuje domyślnego profilu."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()
        await store.ensure_defaults()
        await store.ensure_defaults()

        prompts = await store.list_all()
        assert len(prompts) == 1


# ---------------------------------------------------------------------------
# Testy CRUD
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_prompt() -> None:
    """Tworzenie nowego profilu i weryfikacja jego pól."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        instance = await store.create(
            name="Dom",
            content="Jesteś asystentem domowym.",
            description="Profil na co dzień.",
            custom_id="profile_home",
        )

        assert instance.id == "profile_home"
        assert instance.name == "Dom"
        assert instance.content == "Jesteś asystentem domowym."
        assert instance.description == "Profil na co dzień."


@pytest.mark.anyio
async def test_create_prompt_with_set_active() -> None:
    """Nowy profil tworzony z set_active=True staje się od razu aktywny."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.create(
            name="Nowy Aktywny",
            content="Nowy profil.",
            custom_id="profile_new",
            set_active=True,
        )

        active_id = await store.get_active_id()
        assert active_id == "profile_new"


@pytest.mark.anyio
async def test_create_prompt_enforces_max_three_profiles() -> None:
    """Próba utworzenia 4. profilu (ponad domyślny) rzuca ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()  # profile_1 (1/3)
        await store.create(name="Drugi", content="...", custom_id="profile_2")  # 2/3
        await store.create(name="Trzeci", content="...", custom_id="profile_3")  # 3/3

        with pytest.raises(ValueError, match="limit"):
            await store.create(name="Czwarty", content="...", custom_id="profile_4")


@pytest.mark.anyio
async def test_get_existing_prompt() -> None:
    """Pobieranie istniejącego profilu zwraca poprawny obiekt."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        instance = await store.get("profile_1")
        assert instance is not None
        assert instance.id == "profile_1"


@pytest.mark.anyio
async def test_get_nonexistent_prompt_returns_none() -> None:
    """Pobieranie nieistniejącego ID zwraca None."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        result = await store.get("profile_nonexistent")
        assert result is None


@pytest.mark.anyio
async def test_update_prompt() -> None:
    """Aktualizacja nazwy i treści profilu persystuje zmiany na dysku."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.update("profile_1", name="Zmieniona Nazwa", content="Nowa treść.")

        updated = await store.get("profile_1")
        assert updated is not None
        assert updated.name == "Zmieniona Nazwa"
        assert updated.content == "Nowa treść."


@pytest.mark.anyio
async def test_update_nonexistent_prompt_raises() -> None:
    """Próba aktualizacji nieistniejącego profilu rzuca ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        with pytest.raises(ValueError, match="nie istnieje"):
            await store.update("profile_ghost", name="X")


@pytest.mark.anyio
async def test_delete_inactive_prompt() -> None:
    """Usunięcie nieaktywnego profilu zwraca True i usuwa plik z dysku."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.create(name="Do usunięcia", content="...", custom_id="profile_temp")
        result = await store.delete("profile_temp")

        assert result is True
        assert await store.get("profile_temp") is None


@pytest.mark.anyio
async def test_delete_active_prompt_raises() -> None:
    """Próba usunięcia aktywnego profilu rzuca ValueError z odpowiednim komunikatem."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        with pytest.raises(ValueError, match="aktywnego profilu"):
            await store.delete("profile_1")


@pytest.mark.anyio
async def test_delete_nonexistent_prompt_returns_false() -> None:
    """Próba usunięcia nieistniejącego profilu zwraca False (bez wyjątku)."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        result = await store.delete("profile_nonexistent_xyz")
        assert result is False


# ---------------------------------------------------------------------------
# Testy set_active
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_set_active_changes_active_id() -> None:
    """set_active() zmienia aktywny profil i persystuje to na dysku."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()
        await store.create(name="Drugi", content="Treść.", custom_id="profile_second")

        await store.set_active("profile_second")

        active_id = await store.get_active_id()
        assert active_id == "profile_second"


@pytest.mark.anyio
async def test_set_active_nonexistent_raises() -> None:
    """set_active() z nieistniejącym ID rzuca ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        with pytest.raises(ValueError, match="nie istnieje"):
            await store.set_active("profile_ghost")


# ---------------------------------------------------------------------------
# Testy get_active_content i fallbacku
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_active_content_returns_empty_by_default() -> None:
    """get_active_content() zwraca pusty string dla domyślnego (nieskonfigurowanego) profilu."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        content = await store.get_active_content()
        assert content == ""


@pytest.mark.anyio
async def test_get_active_content_after_update() -> None:
    """get_active_content() zwraca zaktualizowaną treść po edycji aktywnego profilu."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.update("profile_1", content="Jesteś Regisem, asystentem domowym.")
        content = await store.get_active_content()
        assert content == "Jesteś Regisem, asystentem domowym."


@pytest.mark.anyio
async def test_get_active_content_after_switch() -> None:
    """get_active_content() zwraca treść nowo aktywowanego profilu."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.create(name="Kreatywny", content="Jesteś kreatywnym asystentem.", custom_id="profile_creative")
        await store.set_active("profile_creative")

        content = await store.get_active_content()
        assert content == "Jesteś kreatywnym asystentem."


# ---------------------------------------------------------------------------
# AgentDefaultPromptStore — fallback kernela, jedna wartość, bez CRUD
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_agent_default_prompt_seeds_with_default_system_prompt() -> None:
    """Przy pustym katalogu get_content() zasiewa i zwraca DEFAULT_SYSTEM_PROMPT."""
    with tempfile.TemporaryDirectory() as tmp:
        store = AgentDefaultPromptStore(data_dir=Path(tmp))
        content = await store.get_content()
        assert content == DEFAULT_SYSTEM_PROMPT


@pytest.mark.anyio
async def test_agent_default_prompt_set_and_get() -> None:
    """set_content() persystuje treść, kolejny get_content() ją zwraca."""
    with tempfile.TemporaryDirectory() as tmp:
        store = AgentDefaultPromptStore(data_dir=Path(tmp))
        await store.set_content("Jestem prostym fallbackiem.")

        content = await store.get_content()
        assert content == "Jestem prostym fallbackiem."


@pytest.mark.anyio
async def test_agent_default_prompt_migrates_from_legacy_active_prompt() -> None:
    """Jeśli istnieją legacy pliki data/prompts/*.json + active_prompt.json, seed pochodzi z nich."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        legacy_dir = tmp_path / "prompts"
        legacy_dir.mkdir()
        (legacy_dir / "prompt_default.json").write_text(
            '{"name": "Legacy", "content": "Legacy treść promptu.", "description": null}',
            encoding="utf-8",
        )
        (tmp_path / "active_prompt.json").write_text('{"active_id": "prompt_default"}', encoding="utf-8")

        store = AgentDefaultPromptStore(data_dir=tmp_path)
        content = await store.get_content()
        assert content == "Legacy treść promptu."
