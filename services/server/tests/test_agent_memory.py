import tempfile
import time
from pathlib import Path

from server.agent.memory import MemoryManager, Session, generate_session_id


def test_session_id_generation() -> None:
    session_id = generate_session_id()
    assert session_id.startswith("session_")
    assert len(session_id) == 16  # 'session_' + 8 hex chars = 16 chars


def test_session_creation_and_title() -> None:
    session = Session(session_id="session_12345678", title="Moja Testowa Sesja")
    assert session.session_id == "session_12345678"
    assert session.title == "Moja Testowa Sesja"
    assert len(session.messages) == 0

    msg1 = session.add_message(role="user", content="Cześć Agent")
    assert msg1.role == "user"
    assert msg1.content == "Cześć Agent"
    assert len(session.messages) == 1


def test_memory_manager_persistence_and_titles() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Tworzymy MemoryManager w pustym katalogu (powinna powstać domyślna sesja)
        memory1 = MemoryManager(data_dir=tmp_path)
        summaries = memory1.list_session_summaries()
        assert len(summaries) == 1
        assert summaries[0].session_id == "session_default"
        assert summaries[0].title == "Główny Czat Debugujący"

        # 2. Tworzymy nową sesję z unikalnym ID
        new_sess = memory1.create_session(title="Rozmowa z Satelitą")
        assert new_sess.session_id.startswith("session_")
        assert new_sess.title == "Rozmowa z Satelitą"

        # Dodajemy wiadomość do nowej sesji
        memory1.add_message(session_id=new_sess.session_id, role="user", content="Testowa treść")

        # 3. Symulujemy restart serwera – wczytanie z dysku
        memory2 = MemoryManager(data_dir=tmp_path)
        loaded_summaries = memory2.list_session_summaries()
        assert len(loaded_summaries) == 2

        # Pobieramy historię dla nowo utworzonej sesji po restarcie
        history = memory2.get_history(new_sess.session_id)
        assert len(history) == 1
        assert history[0].content == "Testowa treść"

        # 4. Zmiana nazwy sesji (title)
        memory2.update_session_title(new_sess.session_id, "Zmieniona Nazwa Sesji")
        updated_sess = memory2.get_or_create_session(new_sess.session_id)
        assert updated_sess.title == "Zmieniona Nazwa Sesji"

        # 5. Usunięcie sesji
        deleted = memory2.delete_session(new_sess.session_id)
        assert deleted is True
        assert len(memory2.list_session_summaries()) == 1


# ------------------------------------------------------------------------------
# Wygaszanie sesji po bezczynności (`Session.idle_ttl_seconds`)
# ------------------------------------------------------------------------------


def test_fresh_session_with_ttl_is_not_expired() -> None:
    """Sesja używana przed chwilą zachowuje historię, choć ma ustawiony TTL."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = MemoryManager(data_dir=Path(tmp_dir))
        memory.add_message(session_id="sat_abc", role="user", content="Cześć")

        session = memory.get_or_create_session("sat_abc", idle_ttl_seconds=300.0)

        assert len(session.messages) == 1


def test_stale_session_is_cleared_but_keeps_identity() -> None:
    """Przeterminowana sesja traci HISTORIĘ, ale nie tożsamość — satelita jest
    rozpoznawana po `session_id` równym swojemu `sender_id`."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = MemoryManager(data_dir=Path(tmp_dir))
        memory.create_session(title="Satelita salon", custom_id="sat_abc", idle_ttl_seconds=300.0)
        memory.add_message(session_id="sat_abc", role="user", content="Zgaś światło")
        created_at = memory.get_or_create_session("sat_abc").created_at

        # Cofamy ostatnią aktywność o godzinę — jedyny stan, na którym opiera się reguła
        memory.get_or_create_session("sat_abc").updated_at = time.time() - 3600

        session = memory.get_or_create_session("sat_abc")

        assert session.messages == []
        assert session.session_id == "sat_abc"
        assert session.title == "Satelita salon"
        assert session.created_at == created_at


def test_expiry_survives_restart_and_is_persisted() -> None:
    """TTL jest polem sesji, więc przeżywa restart procesu, a wyczyszczenie historii
    trafia na dysk (a nie tylko do pamięci RAM)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        memory1 = MemoryManager(data_dir=tmp_path)
        memory1.create_session(custom_id="sat_abc", idle_ttl_seconds=300.0)
        memory1.add_message(session_id="sat_abc", role="user", content="Zgaś światło")
        memory1.get_or_create_session("sat_abc").updated_at = time.time() - 3600
        memory1.save_session("sat_abc")

        memory2 = MemoryManager(data_dir=tmp_path)
        assert memory2.get_or_create_session("sat_abc").idle_ttl_seconds == 300.0
        assert memory2.get_history("sat_abc") == []

        memory3 = MemoryManager(data_dir=tmp_path)
        assert memory3.get_history("sat_abc") == []


def test_session_without_ttl_never_expires() -> None:
    """Domyślny brak TTL-a (czat Web UI) — historia przeżywa dowolną przerwę."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = MemoryManager(data_dir=Path(tmp_dir))
        memory.add_message(session_id="session_default", role="user", content="Stara wiadomość")
        memory.get_or_create_session("session_default").updated_at = time.time() - 86400 * 30

        assert len(memory.get_history("session_default")) == 1


def test_none_ttl_does_not_clear_policy_set_by_another_caller() -> None:
    """`idle_ttl_seconds=None` znaczy „nie mam zdania", nie „wyłącz wygaszanie" —
    inaczej jedno wejście z Web UI zdejmowałoby politykę satelicie."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = MemoryManager(data_dir=Path(tmp_dir))
        memory.create_session(custom_id="sat_abc", idle_ttl_seconds=300.0)

        memory.get_or_create_session("sat_abc")

        assert memory.get_or_create_session("sat_abc").idle_ttl_seconds == 300.0


def test_zero_ttl_disables_expiry() -> None:
    """0 w konfiguracji = wyłączone; brzeg kompozycji podaje surową wartość."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = MemoryManager(data_dir=Path(tmp_dir))
        memory.create_session(custom_id="sat_abc", idle_ttl_seconds=0)
        memory.add_message(session_id="sat_abc", role="user", content="Stara wiadomość")
        memory.get_or_create_session("sat_abc").updated_at = time.time() - 86400

        assert memory.get_or_create_session("sat_abc", idle_ttl_seconds=0).idle_ttl_seconds is None
        assert len(memory.get_history("sat_abc")) == 1


def test_new_message_is_not_wiped_by_its_own_expiry() -> None:
    """Kolejność w `add_message`: najpierw wygaszenie starej historii, potem dopisanie
    nowej wiadomości. Odwrotna kasowałaby świeże pytanie użytkownika."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = MemoryManager(data_dir=Path(tmp_dir))
        memory.create_session(custom_id="sat_abc", idle_ttl_seconds=300.0)
        memory.add_message(session_id="sat_abc", role="user", content="Stara wiadomość")
        memory.get_or_create_session("sat_abc").updated_at = time.time() - 3600

        memory.add_message(session_id="sat_abc", role="user", content="Nowe pytanie")

        history = memory.get_history("sat_abc")
        assert [m.content for m in history] == ["Nowe pytanie"]


# ------------------------------------------------------------------------------
# Sufit utrwalanych wiadomości (`max_persisted_messages`)
# ------------------------------------------------------------------------------


def test_history_is_trimmed_to_persisted_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = MemoryManager(data_dir=Path(tmp_dir), max_persisted_messages=5)
        for i in range(12):
            memory.add_message(session_id="session_default", role="user", content=f"wiadomość {i}")

        history = memory.get_history("session_default")

        assert len(history) == 5
        assert [m.content for m in history] == [f"wiadomość {i}" for i in range(7, 12)]


def test_trimming_is_disabled_without_limit() -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        memory = MemoryManager(data_dir=Path(tmp_dir), max_persisted_messages=0)
        for i in range(30):
            memory.add_message(session_id="session_default", role="user", content=f"wiadomość {i}")

        assert len(memory.get_history("session_default")) == 30
