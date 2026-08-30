import time
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from shared import ChatMessageDTO, ChatSessionSummaryDTO, ConfigStore, get_logger, sanitize_identifier
from shared import data_dir as shared_data_dir

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
    idle_ttl_seconds: float | None = Field(
        default=None,
        description="Po ilu sekundach bezczynności historia tej sesji jest czyszczona. "
        "None = sesja nie wygasa nigdy (domyślne — czat Web UI, którym zarządza użytkownik).",
    )


class Session:
    """Reprezentacja pojedynczej sesji konwersacyjnej w kernelu Regis."""

    def __init__(
        self,
        session_id: str,
        title: str = "Nowa konwersacja",
        created_at: float | None = None,
        updated_at: float | None = None,
        messages: list[ChatMessageDTO] | None = None,
        idle_ttl_seconds: float | None = None,
    ) -> None:
        self.session_id: str = session_id
        self.title: str = title
        self.created_at: float = created_at if created_at is not None else time.time()
        self.updated_at: float = updated_at if updated_at is not None else time.time()
        self.messages: list[ChatMessageDTO] = messages or []
        self.idle_ttl_seconds: float | None = idle_ttl_seconds

    def is_stale(self, now: float | None = None) -> bool:
        """Czy sesja przekroczyła własny limit bezczynności.

        Czysta funkcja stanu — `updated_at` odświeża każde dopisanie wiadomości, więc
        żaden timer ani wątek w tle nie jest potrzebny (patrz `MemoryManager`)."""
        if self.idle_ttl_seconds is None:
            return False
        return (now or time.time()) - self.updated_at > self.idle_ttl_seconds

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
            idle_ttl_seconds=self.idle_ttl_seconds,
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
            idle_ttl_seconds=model.idle_ttl_seconds,
        )


class MemoryManager:
    """Centralny zarządca pamięci sesji i trwałości historii konwersacji w kernelu Regis.

    Przechowuje sesje w pamięci RAM oraz utrwala je na dysku
    w plikach JSON w katalogu `data/sessions/` przy użyciu ConfigStore z pakietu shared.

    **Dwie reguły przeciw nieskończonemu narastaniu historii** — obie mieszkają tutaj,
    a nie u wywołującego, bo obowiązują każdego klienta kernela (Web UI, satelitę,
    skrypt), nie jedną bramkę:

    * **wygaszanie po bezczynności** — `Session.idle_ttl_seconds`, sprawdzane leniwie
      przy następnym sięgnięciu po sesję (`get_or_create_session`). Bez timera i bez
      wątku w tle, bo `updated_at` niesie już całą potrzebną informację. Politykę
      ustawia brzeg kompozycji: satelity dostają wartość z `Settings`, czat Web UI nie
      dostaje żadnej i nie wygasa nigdy;
    * **sufit liczby utrwalanych wiadomości** — `max_persisted_messages`, przycinany
      przy każdym dopisaniu. Dotyczy też sesji bez TTL-a, czyli chroni plik na dysku
      nawet tam, gdzie historia ma żyć długo.

    Te reguły są niezależne od `ContextBuilder.max_history_messages`, który przycina
    to, co idzie do modelu — tu chodzi o rozmiar i świeżość samej pamięci.
    """

    def __init__(
        self,
        data_dir: Path | str | None = None,
        max_persisted_messages: int | None = None,
    ) -> None:
        """:param max_persisted_messages: sufit liczby wiadomości trzymanych w jednej sesji.
            `None` albo wartość <= 0 wyłącza przycinanie."""
        self.max_persisted_messages: int | None = (
            max_persisted_messages if max_persisted_messages and max_persisted_messages > 0 else None
        )
        self.sessions_dir = Path(data_dir).resolve() if data_dir else shared_data_dir(__file__) / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, Session] = {}
        
        # Wczytanie istniejących sesji z pliku i upewnienie się, że istnieje sesja domyślna
        self._load_all_from_disk()

    def _session_file_path(self, session_id: str) -> Path:
        """Zwraca ścieżkę pliku danej sesji, walidując `session_id` przeciwko directory traversal."""
        sanitize_identifier(session_id, field_name="session_id")
        return self.sessions_dir / f"{session_id}.json"

    def _get_store_for_session(self, session_id: str) -> ConfigStore[SessionDataModel]:
        """Zwraca instancję ConfigStore przypisaną do pliku danej sesji."""
        return ConfigStore(SessionDataModel, self._session_file_path(session_id))

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

    @staticmethod
    def _normalize_ttl(value: float | None) -> float | None:
        """`None` oraz wartości <= 0 znaczą to samo: sesja nie wygasa.

        Dzięki temu brzeg kompozycji może podać surową wartość z konfiguracji (gdzie
        `0` jest naturalnym sposobem wyłączenia mechanizmu) bez tłumaczenia jej na `None`."""
        return value if value is not None and value > 0 else None

    def create_session(
        self,
        title: str = "Nowa konwersacja",
        custom_id: str | None = None,
        idle_ttl_seconds: float | None = None,
    ) -> Session:
        """Tworzy nową sesję konwersacyjną z unikalnym ID w formacie session_{hex8} i zapisuje na dysku.

        :param title: Wyświetlana nazwa/tytuł sesji.
        :param custom_id: Opcjonalne własne ID sesji (np. 'session_default').
        :param idle_ttl_seconds: Limit bezczynności tej sesji; `None`/<=0 = bez wygaszania.
        :return: Utworzona obiektowa instancja Session.
        """
        session_id = custom_id or generate_session_id()
        if custom_id:
            sanitize_identifier(custom_id, field_name="custom_id")
        session = Session(session_id=session_id, title=title, idle_ttl_seconds=self._normalize_ttl(idle_ttl_seconds))
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

    def get_or_create_session(
        self,
        session_id: str = "session_default",
        idle_ttl_seconds: float | None = None,
    ) -> Session:
        """Pobiera istniejącą sesję lub tworzy nową jeśli podane ID nie istnieje.

        Przy okazji **wygasza sesję przeterminowaną** — to jedyny moment, w którym
        sprawdzenie jest potrzebne, bo sesja, po którą nikt nie sięga, nikomu nie szkodzi.

        :param idle_ttl_seconds: Polityka bezczynności wnoszona przez wywołującego.
            `None` znaczy „nie mam zdania" i **nie kasuje** polityki już zapisanej
            w sesji — inaczej pojedyncze wywołanie z Web UI zdejmowałoby TTL satelicie.
            Wartość niepusta nadpisuje zapisaną, żeby zmiana ustawienia działała od
            razu, bez migracji plików sesji.
        """
        if session_id not in self._sessions:
            sanitize_identifier(session_id, field_name="session_id")
            file_path = self._session_file_path(session_id)
            if file_path.exists():
                store = ConfigStore(SessionDataModel, file_path)
                data_model = store.load()
                self._sessions[session_id] = Session.from_model(data_model)
            else:
                return self.create_session(
                    title="Nowa konwersacja", custom_id=session_id, idle_ttl_seconds=idle_ttl_seconds
                )

        session = self._sessions[session_id]
        if idle_ttl_seconds is not None:
            session.idle_ttl_seconds = self._normalize_ttl(idle_ttl_seconds)
        self._expire_if_stale(session)
        return session

    def _expire_if_stale(self, session: Session) -> bool:
        """Czyści historię sesji, która przekroczyła własny limit bezczynności.

        **ID, tytuł i `created_at` zostają** — satelita jest rozpoznawana po
        `sender_id` równym `session_id`, więc rotacja identyfikatora zerwałaby jej
        tożsamość w rejestrze klientów. Czyszczona jest wyłącznie historia, czyli
        dokładnie ta rzecz, która się zestarzała: bez tego model dostawał
        `max_history_messages` wiadomości sprzed wielu godzin jako „bieżącą rozmowę".

        :return: True, jeśli historia została wyczyszczona.
        """
        if not session.is_stale() or not session.messages:
            return False
        idle_seconds = time.time() - session.updated_at
        logger.info(
            f"Sesja '{session.session_id}' bezczynna przez {idle_seconds:.0f}s "
            f"(limit: {session.idle_ttl_seconds:.0f}s) — historia ({len(session.messages)} wiadomości) wyczyszczona."
        )
        session.clear()
        self.save_session(session.session_id)
        return True

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
        """Dodaje wiadomość do wskazanej sesji i utrwala zmianę na dysku.

        Kolejność jest istotna: `get_or_create_session()` może w tym momencie wygasić
        przeterminowaną historię, a dopiero potem dopisujemy nową wiadomość — więc
        świeże pytanie użytkownika nigdy nie pada ofiarą własnego wygaszenia.
        """
        session = self.get_or_create_session(session_id)
        msg = session.add_message(role=role, content=content, metadata=metadata)
        self._trim_to_limit(session)
        self.save_session(session_id)
        return msg

    def _trim_to_limit(self, session: Session) -> None:
        """Utrzymuje sufit `max_persisted_messages` najnowszych wiadomości w sesji.

        Świadoma strata: najstarsze wiadomości znikają z historii nieodwracalnie, także
        z widoku w Web UI. Alternatywą jest plik sesji rosnący bez końca — satelita
        używa jednego `session_id` przez cały czas swojego istnienia."""
        limit = self.max_persisted_messages
        if limit is None or len(session.messages) <= limit:
            return
        removed = len(session.messages) - limit
        del session.messages[:removed]
        logger.debug(f"Sesja '{session.session_id}': przycięto {removed} najstarszych wiadomości (limit: {limit}).")

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
        sanitize_identifier(session_id, field_name="session_id")
        if session_id in self._sessions:
            del self._sessions[session_id]

        file_path = self._session_file_path(session_id)
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
