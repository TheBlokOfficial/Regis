"""Testy jednostkowe dla PromptStore — CRUD, blokady i mechanizm fallbacku."""

import tempfile
from pathlib import Path

import pytest

from server.agent.context.builder import DEFAULT_SYSTEM_PROMPT
from server.agent.prompts import PromptStore
from server.agent.prompts.models import PromptFileContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_store(tmp_path: Path) -> PromptStore:
    """Tworzy izolowaną instancję PromptStore w tymczasowym katalogu."""
    return PromptStore(data_dir=tmp_path)


# ---------------------------------------------------------------------------
# Testy inicjalizacji i domyślnego promptu
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_ensure_defaults_creates_default_prompt() -> None:
    """Przy pustym katalogu ensure_defaults() tworzy plik prompt_default.json."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        prompts = await store.list_all()
        assert len(prompts) == 1
        assert prompts[0].id == "prompt_default"
        assert prompts[0].content == DEFAULT_SYSTEM_PROMPT


@pytest.mark.anyio
async def test_ensure_defaults_sets_active_id() -> None:
    """ensure_defaults() ustawia prompt_default jako aktywny."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        active_id = await store.get_active_id()
        assert active_id == "prompt_default"


@pytest.mark.anyio
async def test_ensure_defaults_idempotent() -> None:
    """Wielokrotne wywołanie ensure_defaults() nie duplikuje domyślnego promptu."""
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
    """Tworzenie nowego promptu i weryfikacja jego pól."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        instance = await store.create(
            name="Prompt Kodujący",
            content="Jesteś ekspertem Python.",
            description="Do zadań kodowania.",
            custom_id="prompt_coding",
        )

        assert instance.id == "prompt_coding"
        assert instance.name == "Prompt Kodujący"
        assert instance.content == "Jesteś ekspertem Python."
        assert instance.description == "Do zadań kodowania."


@pytest.mark.anyio
async def test_create_prompt_with_set_active() -> None:
    """Nowy prompt tworzony z set_active=True staje się od razu aktywnym."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.create(
            name="Nowy Aktywny",
            content="Nowy prompt.",
            custom_id="prompt_new",
            set_active=True,
        )

        active_id = await store.get_active_id()
        assert active_id == "prompt_new"


@pytest.mark.anyio
async def test_get_existing_prompt() -> None:
    """Pobieranie istniejącego promptu zwraca poprawny obiekt."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        instance = await store.get("prompt_default")
        assert instance is not None
        assert instance.id == "prompt_default"


@pytest.mark.anyio
async def test_get_nonexistent_prompt_returns_none() -> None:
    """Pobieranie nieistniejącego ID zwraca None."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        result = await store.get("prompt_nonexistent")
        assert result is None


@pytest.mark.anyio
async def test_update_prompt() -> None:
    """Aktualizacja nazwy i treści promptu persystuje zmiany na dysku."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.update("prompt_default", name="Zmieniona Nazwa", content="Nowa treść.")

        updated = await store.get("prompt_default")
        assert updated is not None
        assert updated.name == "Zmieniona Nazwa"
        assert updated.content == "Nowa treść."


@pytest.mark.anyio
async def test_update_nonexistent_prompt_raises() -> None:
    """Próba aktualizacji nieistniejącego promptu rzuca ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        with pytest.raises(ValueError, match="nie istnieje"):
            await store.update("prompt_ghost", name="X")


@pytest.mark.anyio
async def test_delete_inactive_prompt() -> None:
    """Usunięcie nieaktywnego promptu zwraca True i usuwa plik z dysku."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.create(name="Do usunięcia", content="...", custom_id="prompt_temp")
        result = await store.delete("prompt_temp")

        assert result is True
        assert await store.get("prompt_temp") is None


@pytest.mark.anyio
async def test_delete_active_prompt_raises() -> None:
    """Próba usunięcia aktywnego promptu rzuca ValueError z odpowiednim komunikatem."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        with pytest.raises(ValueError, match="aktywnego promptu"):
            await store.delete("prompt_default")


@pytest.mark.anyio
async def test_delete_nonexistent_prompt_returns_false() -> None:
    """Próba usunięcia nieistniejącego promptu zwraca False (bez wyjątku)."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        result = await store.delete("prompt_nonexistent_xyz")
        assert result is False


# ---------------------------------------------------------------------------
# Testy set_active
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_set_active_changes_active_id() -> None:
    """set_active() zmienia aktywny prompt i persystuje to na dysku."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()
        await store.create(name="Drugi", content="Treść.", custom_id="prompt_second")

        await store.set_active("prompt_second")

        active_id = await store.get_active_id()
        assert active_id == "prompt_second"


@pytest.mark.anyio
async def test_set_active_nonexistent_raises() -> None:
    """set_active() z nieistniejącym ID rzuca ValueError."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        with pytest.raises(ValueError, match="nie istnieje"):
            await store.set_active("prompt_ghost")


# ---------------------------------------------------------------------------
# Testy get_active_content i fallbacku
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_active_content_returns_default_prompt() -> None:
    """get_active_content() zwraca treść domyślnego promptu po inicjalizacji."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        content = await store.get_active_content()
        assert content == DEFAULT_SYSTEM_PROMPT


@pytest.mark.anyio
async def test_get_active_content_after_update() -> None:
    """get_active_content() zwraca zaktualizowaną treść po edycji aktywnego promptu."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.update("prompt_default", content="Nowy prompt produkcyjny.")
        content = await store.get_active_content()
        assert content == "Nowy prompt produkcyjny."


@pytest.mark.anyio
async def test_get_active_content_after_switch() -> None:
    """get_active_content() zwraca treść nowo aktywowanego promptu."""
    with tempfile.TemporaryDirectory() as tmp:
        store = make_store(Path(tmp))
        await store.ensure_defaults()

        await store.create(name="Kreatywny", content="Jesteś kreatywnym asystentem.", custom_id="prompt_creative")
        await store.set_active("prompt_creative")

        content = await store.get_active_content()
        assert content == "Jesteś kreatywnym asystentem."
