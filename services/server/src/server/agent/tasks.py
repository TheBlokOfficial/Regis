"""Rejestr zadań w tle — po jednym na sesję, plus bufor generowanego tekstu.

Wydzielone z `AgentEngine`, bo to odrębna odpowiedzialność: „która sesja właśnie
pracuje i co zdążyła napisać" nie ma nic wspólnego z budowaniem kontekstu ani
z pętlą ReAct. `AgentEngine` trzymał to jako dwa równoległe słowniki
(`_active_tasks`, `_generation_buffers`), które trzeba było pamiętać sprzątać
w tym samym `finally`.

Bufor jest tu, a nie w `TurnRunner`, bo czyta go ktoś **z zewnątrz** tury:
`GET /chat/sessions/{id}/history` dokleja go jako wiadomość częściową, gdy karta
przeglądarki dołącza do sesji, która już generuje.
"""

from __future__ import annotations

import asyncio
from typing import Any

from shared import get_logger

logger = get_logger("regis.agent.tasks")


class SessionTaskRegistry:
    """Jedno miejsce prawdy o tym, które sesje generują odpowiedź."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._buffers: dict[str, str] = {}

    def is_busy(self, session_id: str) -> bool:
        task = self._tasks.get(session_id)
        return task is not None and not task.done()

    def register(self, session_id: str, task: asyncio.Task[Any]) -> None:
        self._tasks[session_id] = task

    def start_buffer(self, session_id: str) -> None:
        self._buffers[session_id] = ""

    def append_to_buffer(self, session_id: str, chunk: str) -> None:
        self._buffers[session_id] = self._buffers.get(session_id, "") + chunk

    def buffer_length(self, session_id: str) -> int:
        """Długość dotychczasowego tekstu odpowiedzi — na niej liczą się `text_offset`
        kroków narzędzi i przebiegów rozumowania."""
        return len(self._buffers.get(session_id, ""))

    def buffer(self, session_id: str) -> str:
        return self._buffers.get(session_id, "")

    def buffer_if_busy(self, session_id: str) -> str | None:
        """Bufor tylko dla sesji realnie generującej — `None` oznacza „nic się nie dzieje",
        a nie „pusta odpowiedź", więc wywołujący nie musi tego rozróżniać sam."""
        return self._buffers.get(session_id, "") if self.is_busy(session_id) else None

    def release(self, session_id: str) -> None:
        """Sprzątnięcie po zakończonej turze — zadanie i bufor razem, bo rozjazd
        między nimi objawiłby się sesją na zawsze „zajętą" albo buforem-widmem."""
        self._tasks.pop(session_id, None)
        self._buffers.pop(session_id, None)

    def active_session_ids(self) -> list[str]:
        return list(self._tasks.keys())

    async def cancel(self, session_id: str) -> bool:
        """Anuluje zadanie sesji i **czeka na jego zakończenie**.

        :return: True jeśli było co anulować, False gdy sesja nie pracowała.
        """
        task = self._tasks.get(session_id)
        if task is None or task.done():
            return False
        logger.info(f"Anulowanie aktywnego zadania dla sesji '{session_id}'...")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        return True
