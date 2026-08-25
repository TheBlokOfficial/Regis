"""Trwały magazyn zrzutów wywołań LLM — jedyne w projekcie miejsce z bazą SQLite.

**Dlaczego nie JSON, jak reszta stanu.** Cała konfiguracja Regisa (`ConfigStore`,
`JsonInstanceRepository`) siedzi w plikach JSON i to jest dla niej właściwe: kilka
wpisów, cykl „wczytaj-zmień-zapisz", plik da się otworzyć edytorem. Telemetria ma
odwrotny profil: tysiące rekordów, wyłącznie dopisywanie, odczyt zawsze z filtrem
i sortowaniem po czasie, plus rotacja. `JsonInstanceRepository` oznaczałby `glob()`
po tysiącach plików przy każdym otwarciu zakładki. To inny problem, więc inny
magazyn — świadomy precedens, nie niekonsekwencja (patrz `docs/manifest.md`).

**Zapis nigdy nie opóźnia tury.** `submit()` jest synchroniczne i nieblokujące:
wrzuca rekord do kolejki i wraca. Pełna kolejka oznacza porzucenie najstarszego
wpisu — telemetria jest obserwatorem, więc jej przeciążenie ma kosztować utratę
własnych danych, nigdy spowolnienie generowania odpowiedzi. Z tego samego powodu
każdy wyjątek writera kończy w logu i nie leci wyżej.

Połączenie otwierane jest per operacja, wewnątrz `asyncio.to_thread`: połączenia
SQLite są przypisane do wątku, a pula wątków `to_thread` nie gwarantuje tego
samego wątku między wywołaniami. WAL sprawia, że równoległy czytelnik nie czeka
na writera.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from shared import (
    GenerationAttemptDTO,
    GenerationLogDetailDTO,
    GenerationLogEntryDTO,
    GenerationLogListResponse,
    GenerationMessageDTO,
    get_logger,
)

from server.telemetry.models import GenerationRecord, enforce_size_limit

logger = get_logger("regis.telemetry.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS generations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at       REAL    NOT NULL,
    session_id       TEXT,
    turn_id          TEXT,
    call_index       INTEGER NOT NULL DEFAULT 0,
    sender_id        TEXT,
    model            TEXT,
    provider_type    TEXT,
    instance_id      TEXT,
    instance_name    TEXT,
    status           TEXT    NOT NULL,
    finish_reason    TEXT,
    error            TEXT,
    prompt_tokens    INTEGER,
    completion_tokens INTEGER,
    cached_tokens    INTEGER,
    estimated        INTEGER NOT NULL DEFAULT 1,
    ttft_ms          REAL,
    total_ms         REAL,
    output_tps       REAL,
    tool_calls       INTEGER NOT NULL DEFAULT 0,
    message_count    INTEGER NOT NULL DEFAULT 0,
    attempt_count    INTEGER NOT NULL DEFAULT 0,
    truncated        INTEGER NOT NULL DEFAULT 0,
    messages_json    TEXT    NOT NULL,
    tools_json       TEXT    NOT NULL,
    attempts_json    TEXT    NOT NULL,
    answer           TEXT    NOT NULL DEFAULT '',
    reasoning        TEXT    NOT NULL DEFAULT '',
    response_tool_calls_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_generations_created_at ON generations (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_generations_turn ON generations (session_id, turn_id, call_index);
"""

_ENTRY_COLUMNS = (
    "id, created_at, session_id, turn_id, call_index, model, provider_type, instance_name, "
    "status, finish_reason, prompt_tokens, completion_tokens, cached_tokens, estimated, "
    "ttft_ms, total_ms, output_tps, tool_calls, message_count, attempt_count, truncated"
)

_ADDED_COLUMNS = (
    ("answer", "TEXT NOT NULL DEFAULT ''"),
    ("reasoning", "TEXT NOT NULL DEFAULT ''"),
    ("response_tool_calls_json", "TEXT NOT NULL DEFAULT '[]'"),
)
"""Kolumny dołożone po pierwszym wydaniu schematu — patrz `_add_missing_columns`."""

_WRITE_BATCH = 32
"""Ile rekordów writer scala w jedną transakcję, gdy kolejka zdążyła urosnąć."""

_PRUNE_EVERY = 50
"""Rotacja jest leniwa — uruchamiana co N zapisów, a nie z timera ani osobnego wątku."""


class GenerationLogStore:
    """Kolejka zapisu + zapytania listujące nad jedną tabelą SQLite."""

    def __init__(
        self,
        db_path: Path,
        retention_records: int = 2000,
        max_record_bytes: int = 262144,
        queue_size: int = 256,
    ) -> None:
        self._db_path = db_path
        self._retention_records = retention_records
        self._max_record_bytes = max_record_bytes
        self._queue: asyncio.Queue[GenerationRecord | None] = asyncio.Queue(maxsize=queue_size)
        self._writer: asyncio.Task[None] | None = None
        self._since_prune = 0

    # --------------------------------------------------------------------------
    # Cykl życia
    # --------------------------------------------------------------------------

    async def start(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._init_schema)
        self._writer = asyncio.create_task(self._writer_loop())
        logger.info(f"Telemetria wywołań LLM gotowa [{self._db_path}], retencja: {self._retention_records} rekordów.")

    async def stop(self) -> None:
        """Domyka writera po opróżnieniu kolejki — wpisy z ostatniej tury przed
        zamknięciem serwera to często dokładnie te, których się szuka."""
        if self._writer is None:
            return
        await self._queue.put(None)
        await self._writer
        self._writer = None

    # --------------------------------------------------------------------------
    # Zapis
    # --------------------------------------------------------------------------

    def submit(self, record: GenerationRecord) -> None:
        """Przyjmuje rekord do zapisu. Nie czeka na dysk i nigdy nie rzuca."""
        try:
            self._queue.put_nowait(enforce_size_limit(record, self._max_record_bytes))
        except asyncio.QueueFull:
            # Świadomie porzucamy NAJSTARSZY wpis, nie nowy: przy zatorze bardziej
            # interesuje nas to, co dzieje się teraz.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(enforce_size_limit(record, self._max_record_bytes))
            except (asyncio.QueueEmpty, asyncio.QueueFull):
                logger.warning("Kolejka telemetrii przepełniona — porzucono zrzut wywołania LLM.")
        except Exception as err:
            logger.error(f"Nie udało się zakolejkować zrzutu wywołania LLM: {err}")

    async def _writer_loop(self) -> None:
        while True:
            item = await self._queue.get()
            stopping = item is None
            batch: list[GenerationRecord] = [] if item is None else [item]

            while not self._queue.empty() and len(batch) < _WRITE_BATCH:
                nxt = self._queue.get_nowait()
                if nxt is None:
                    stopping = True
                    continue
                batch.append(nxt)

            if batch:
                try:
                    await asyncio.to_thread(self._insert_batch, batch)
                except Exception as err:
                    logger.error(f"Nie udało się zapisać telemetrii ({len(batch)} rekordów): {err}")

            if stopping:
                return

    # --------------------------------------------------------------------------
    # Odczyt
    # --------------------------------------------------------------------------

    async def list_entries(
        self,
        limit: int = 50,
        before_id: int | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
        status: str | None = None,
    ) -> GenerationLogListResponse:
        rows = await asyncio.to_thread(self._select_entries, limit, before_id, session_id, turn_id, status)
        entries = [GenerationLogEntryDTO(**dict(row)) for row in rows]
        return GenerationLogListResponse(
            entries=entries,
            next_before_id=entries[-1].id if len(entries) == limit else None,
        )

    async def get_entry(self, record_id: int) -> GenerationLogDetailDTO | None:
        row = await asyncio.to_thread(self._select_one, record_id)
        if row is None:
            return None
        data = dict(row)
        return GenerationLogDetailDTO(
            **{k: v for k, v in data.items() if not k.endswith("_json")},
            messages=[GenerationMessageDTO(**m) for m in json.loads(data["messages_json"])],
            tools=json.loads(data["tools_json"]),
            attempts=[GenerationAttemptDTO(**a) for a in json.loads(data["attempts_json"])],
            response_tool_calls=json.loads(data["response_tool_calls_json"]),
        )

    async def clear(self) -> int:
        return await asyncio.to_thread(self._delete_all)

    # --------------------------------------------------------------------------
    # Operacje dyskowe (wołane wyłącznie przez `asyncio.to_thread`)
    # --------------------------------------------------------------------------

    @contextmanager
    def _session(self) -> Iterator[sqlite3.Connection]:
        """Połączenie na jedną operację, **zamykane jawnie**.

        `with sqlite3.connect(...)` domyka wyłącznie transakcję, nie połączenie —
        pomyłka kosztowna nie tylko deskryptorem: dopóki połączenie żyje, Windows
        trzyma plik bazy zablokowany (wychwycone przez testy, które sprzątają katalog
        tymczasowy)."""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._session() as conn:
            # WAL: czytelnik (lista w UI) nie blokuje się na writerze i odwrotnie.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            self._add_missing_columns(conn)

    def _add_missing_columns(self, conn: sqlite3.Connection) -> None:
        """Dokłada kolumny, których brakuje w bazie założonej wcześniejszą wersją.

        `CREATE TABLE IF NOT EXISTS` nie dotyka istniejącej tabeli, więc bez tego
        kroku dotychczasowa baza użytkownika przestałaby przyjmować zapisy po każdym
        rozszerzeniu rekordu. Migracja jest **wyłącznie addytywna** (`ADD COLUMN`
        z wartością domyślną) — stare wpisy zostają, po prostu mają pusty nowy zakres.
        Wystarcza dla telemetrii, bo kolumny tylko przybywają; gdyby kiedyś trzeba
        było zmienić typ albo usunąć kolumnę, to jest miejsce na prawdziwą migrację.
        """
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(generations)")}
        for column, definition in _ADDED_COLUMNS:
            if column not in existing:
                conn.execute(f"ALTER TABLE generations ADD COLUMN {column} {definition}")
                logger.info(f"Telemetria: dołożono kolumnę '{column}' do istniejącej bazy.")

    def _insert_batch(self, batch: list[GenerationRecord]) -> None:
        with self._session() as conn:
            conn.executemany(
                """
                INSERT INTO generations (
                    created_at, session_id, turn_id, call_index, sender_id,
                    model, provider_type, instance_id, instance_name,
                    status, finish_reason, error,
                    prompt_tokens, completion_tokens, cached_tokens, estimated,
                    ttft_ms, total_ms, output_tps, tool_calls,
                    message_count, attempt_count, truncated,
                    messages_json, tools_json, attempts_json,
                    answer, reasoning, response_tool_calls_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [_row_values(record) for record in batch],
            )
            self._since_prune += len(batch)
            if self._since_prune >= _PRUNE_EVERY:
                self._since_prune = 0
                self._prune(conn)

    def _prune(self, conn: sqlite3.Connection) -> None:
        """Zostawia `retention_records` najnowszych wpisów.

        Gdy rekordów jest mniej niż limit, podzapytanie zwraca NULL, a porównanie
        `id < NULL` nie wybiera niczego — brak specjalnego przypadku do obsłużenia."""
        deleted = conn.execute(
            """
            DELETE FROM generations
            WHERE id < (SELECT id FROM generations ORDER BY id DESC LIMIT 1 OFFSET ?)
            """,
            (self._retention_records - 1,),
        ).rowcount
        if deleted > 0:
            logger.debug(f"Rotacja telemetrii: usunięto {deleted} najstarszych wpisów.")

    def _select_entries(
        self,
        limit: int,
        before_id: int | None,
        session_id: str | None,
        turn_id: str | None,
        status: str | None,
    ) -> list[sqlite3.Row]:
        clauses: list[str] = []
        params: list[Any] = []
        for column, value in (
            ("id <", before_id),
            ("session_id =", session_id),
            ("turn_id =", turn_id),
            ("status =", status),
        ):
            if value is not None:
                clauses.append(f"{column} ?")
                params.append(value)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        with self._session() as conn:
            return conn.execute(
                f"SELECT {_ENTRY_COLUMNS} FROM generations {where} ORDER BY id DESC LIMIT ?", params
            ).fetchall()

    def _select_one(self, record_id: int) -> sqlite3.Row | None:
        with self._session() as conn:
            return conn.execute("SELECT * FROM generations WHERE id = ?", (record_id,)).fetchone()

    def _delete_all(self) -> int:
        with self._session() as conn:
            return int(conn.execute("DELETE FROM generations").rowcount)


def _row_values(record: GenerationRecord) -> tuple[Any, ...]:
    """Kolejność musi odpowiadać liście kolumn w `INSERT` wyżej."""
    return (
        record.created_at,
        record.session_id,
        record.turn_id,
        record.call_index,
        record.sender_id,
        record.model,
        record.provider_type,
        record.instance_id,
        record.instance_name,
        record.status,
        record.finish_reason,
        record.error,
        record.prompt_tokens,
        record.completion_tokens,
        record.cached_tokens,
        int(record.estimated),
        record.ttft_ms,
        record.total_ms,
        record.output_tps,
        record.tool_calls,
        len(record.messages),
        len(record.attempts),
        int(record.truncated),
        json.dumps([m.model_dump() for m in record.messages], ensure_ascii=False),
        json.dumps(record.tools, ensure_ascii=False),
        json.dumps([a.model_dump() for a in record.attempts], ensure_ascii=False),
        record.answer,
        record.reasoning,
        json.dumps(record.response_tool_calls, ensure_ascii=False),
    )
