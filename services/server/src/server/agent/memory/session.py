import time
import uuid
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field
from shared import ChatMessageDTO, ChatSessionSummaryDTO, ConfigStore, get_logger, get_service_root

logger = get_logger("regis.agent.memory")


def generate_session_id() -> str:
    """Generuje losowy identyfikator sesji z prefiksem w formacie session_{8_hex_chars}."""
    return f"session_{uuid.uuid4().hex[:8]}"


class SessionDataModel(BaseModel):
    """Model Pydantic reprezentujący stan sesji konwersacyjnej w pliku JSON."""

    session_id: str = Field(..., description="Identyfikator sesji (np. session_a1b2c3d4)")
    title: str = Field(default="Nowa konwersacja", description="Wyświetlana nazwa/tytuł sesji")
    created_at: float = Field(default_factory=time.time, description="Stempel utworzenia sesji")
    updated_at: float = Field(default_factory=time.time, description="Stempel ostatniej modyfikacji")
    messages: list[ChatMessageDTO] = Field(default_factory=list, description="Lista wiadomości w historii sesji")


class Session:
    """Reprezentacja pojedynczej sesji konwersacyjnej w backendzie Agent OS."""

    def __init__(
        self,
        session_id: str,
        title: str = "Nowa konwersacja",
        created_at: float | None = None,
        updated_at: float | None = None,
        messages: list[ChatMessageDTO] | None = None,
    ) -> None:
        self.session_id: str = session_id
        self.title: str = title
        self.created_at: float = created_at if created_at is not None else time.time()
        self.updated_at: float = updated_at if updated_at is not None else time.time()
        self.messages: list[ChatMessageDTO] = messages or []

    def add_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessageDTO:
        """Dodaje nową wiadomość do historii sesji.

        :param role: Rola nadawcy ('user', 'assistant', 'system').
        :param content: Treść wiadomości.
        :param metadata: Opcjonalne dodatkowe metadane.
        :return: Utworzona instancja ChatMessageDTO.
        """
        now = time.time()
        msg = ChatMessageDTO(
            role=role,
            content=content,
            timestamp=now,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        self.updated_at = now
        return msg

    def get_history(self, limit: int | None = None) -> list[ChatMessageDTO]:
        """Pobiera historię wiadomości sesji z opcjonalnym limitem ostatnich wpisów."""
        if limit and limit > 0:
            return self.messages[-limit:]
        return list(self.messages)

    def clear(self) -> None:
        """Czyści całą historię wiadomości sesji."""
        self.messages.clear()
        self.updated_at = time.time()

    def to_model(self) -> SessionDataModel:
        """Konwertuje obiekt sesji do modelu Pydantic do zapisu na dysku."""
        return SessionDataModel(
            session_id=self.session_id,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            messages=self.messages,
        )

    def to_summary(self) -> ChatSessionSummaryDTO:
        """Generuje podsumowanie sesji do listy sesji w API."""
        return ChatSessionSummaryDTO(
            session_id=self.session_id,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            message_count=len(self.messages),
        )

    @classmethod
    def from_model(cls, model: SessionDataModel) -> "Session":
        """Tworzy instancję Session na podstawie zwalidowanego modelu Pydantic z pliku."""
        return cls(
            session_id=model.session_id,
            title=model.title,
            created_at=model.created_at,
            updated_at=model.updated_at,
            messages=model.messages,
        )


class MemoryManager:
    """Centralny zarządca pamięci sesji i trwałości historii konwersacji w Agent OS Kernel.

    Przechowuje sesje w pamięci RAM oraz utrwala je na dysku
    w plikach JSON w katalogu `data/sessions/` przy użyciu ConfigStore z pakietu shared.
    """

    def __init__(self, data_dir: Path | str | None = None) -> None:
        if data_dir:
            self.sessions_dir = Path(data_dir).resolve()
        else:
            service_root = get_service_root(__file__)
            self.sessions_dir = (service_root / "data" / "sessions").resolve()

        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, Session] = {}
        
        # Wczytanie istniejących sesji z pliku i upewnienie się, że istnieje sesja domyślna
        self._load_all_from_disk()

    def _get_store_for_session(self, session_id: str) -> ConfigStore[SessionDataModel]:
        """Zwraca instancję ConfigStore przypisaną do pliku danej sesji."""
        file_path = self.sessions_dir / f"{session_id}.json"
        return ConfigStore(SessionDataModel, file_path)

    def _load_all_from_disk(self) -> None:
        """Automatycznie skanuje katalog data/sessions/ i wczytuje z dysku istniejące sesje."""
        json_files = list(self.sessions_dir.glob("*.json"))
        for file_path in json_files:
            session_id = file_path.stem
            try:
                store = ConfigStore(SessionDataModel, file_path)
                data_model = store.load()
                self._sessions[session_id] = Session.from_model(data_model)
                logger.debug(f"Wczytano sesję '{session_id}' z dysku ('{data_model.title}', {len(data_model.messages)} wiadomości)")
            except Exception as e:
                logger.error(f"Nie udało się wczytać sesji z pliku [{file_path}]: {e}")

        # Jeśli nie ma żadnej sesji, twórz domyślną sesję "session_default"
        if not self._sessions:
            self.create_session(title="Główny Czat Debugujący", custom_id="session_default")

    def create_session(
        self,
        title: str = "Nowa konwersacja",
        custom_id: str | None = None,
    ) -> Session:
        """Tworzy nową sesję konwersacyjną z unikalnym ID w formacie session_{hex8} i zapisuje na dysku.

        :param title: Wyświetlana nazwa/tytuł sesji.
        :param custom_id: Opcjonalne własne ID sesji (np. 'session_default').
        :return: Utworzona obiektowa instancja Session.
        """
        session_id = custom_id or generate_session_id()
        session = Session(session_id=session_id, title=title)
        self._sessions[session_id] = session
        self.save_session(session_id)
        logger.info(f"Utworzono nową sesję konwersacyjną: '{session_id}' ({title})")
        return session

    def save_session(self, session_id: str) -> None:
        """Zapisuje bieżący stan sesji na dysk przy użyciu ConfigStore."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            store = self._get_store_for_session(session_id)
            store.save(session.to_model())

    def get_or_create_session(self, session_id: str = "session_default") -> Session:
        """Pobiera istniejącą sesję lub tworzy nową jeśli podane ID nie istnieje."""
        if session_id not in self._sessions:
            file_path = self.sessions_dir / f"{session_id}.json"
            if file_path.exists():
                store = ConfigStore(SessionDataModel, file_path)
                data_model = store.load()
                self._sessions[session_id] = Session.from_model(data_model)
            else:
                return self.create_session(title="Nowa konwersacja", custom_id=session_id)
        return self._sessions[session_id]

    def update_session_title(self, session_id: str, new_title: str) -> Session:
        """Aktualizuje nazwę wyświetlaną (tytuł) dla podanej sesji i zapisuje na dysku."""
        session = self.get_or_create_session(session_id)
        session.title = new_title
        session.updated_at = time.time()
        self.save_session(session_id)
        return session

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessageDTO:
        """Dodaje wiadomość do wskazanej sesji i utrwala zmianę na dysku."""
        session = self.get_or_create_session(session_id)
        msg = session.add_message(role=role, content=content, metadata=metadata)
        self.save_session(session_id)
        return msg

    def get_history(
        self,
        session_id: str = "session_default",
        limit: int | None = None,
    ) -> list[ChatMessageDTO]:
        """Pobiera historię dla podanego ID sesji."""
        session = self.get_or_create_session(session_id)
        return session.get_history(limit=limit)

    def clear_session(self, session_id: str = "session_default") -> None:
        """Czyści historię wskazanej sesji i zapisuje wyczyszczoną sesję na dysku."""
        if session_id in self._sessions:
            logger.info(f"Czyszczenie pamięci dla sesji: '{session_id}'")
            self._sessions[session_id].clear()
            self.save_session(session_id)

    def delete_session(self, session_id: str) -> bool:
        """Usuwa sesję z pamięci RAM oraz fizycznie kasuje plik JSON z dysku."""
        if session_id in self._sessions:
            del self._sessions[session_id]

        file_path = self.sessions_dir / f"{session_id}.json"
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Usunięto plik sesji z dysku: [{file_path}]")
            return True
        return False

    def list_session_summaries(self) -> list[ChatSessionSummaryDTO]:
        """Zwraca listę podsumowań wszystkich sesji (sortowanych wg najnowszej aktywności)."""
        summaries = [s.to_summary() for s in self._sessions.values()]
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries
