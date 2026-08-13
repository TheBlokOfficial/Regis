import tempfile
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
