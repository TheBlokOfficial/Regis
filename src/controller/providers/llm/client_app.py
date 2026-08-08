import asyncio
import logging
from typing import AsyncGenerator

from controller.endpoints.clients import client_manager
from controller.providers.llm.base import LLMBackend
from controller.exceptions import LLMConnectionError

logger = logging.getLogger(__name__)

# Słownik aktywnych zadań LLM: {task_id: asyncio.Queue}
_pending_tasks: dict[str, asyncio.Queue] = {}


def route_task_event(task_id: str, event: dict) -> None:
    """
    Przekierowuje ramkę task_event z api/clients.py do kolejki oczekującego backendu aplikacji klienckiej.
    """
    q = _pending_tasks.get(task_id)
    if q is not None:
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning(f"[ClientAppBackend] Kolejka dla task_id={task_id} jest pełna — porzucam ramkę.")
    else:
        logger.debug(f"[ClientAppBackend] Odebrano task_event dla nieznanego task_id={task_id} — ignoruję.")


class ClientAppBackend(LLMBackend):
    """
    Dostawca LLM realizujący strumieniowanie przez usługi aplikacji klienckiej (np. Regis Desktop).
    """

    def __init__(self, client_id: str, model_name: str = "nieznany"):
        self.client_id = client_id
        self.model_name = model_name

    def is_available(self) -> bool:
        return bool(self.client_id)

    def get_provider_name(self) -> str:
        return f"client_app ({self.client_id})"

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None
    ) -> AsyncGenerator[dict, None]:
        import uuid
        task_id = str(uuid.uuid4())
        task_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        _pending_tasks[task_id] = task_queue

        ws_payload = {"messages": messages, "tools": tools}
        success = await client_manager.send_command(self.client_id, "chat_stream", {"task_id": task_id, **ws_payload})
        if not success:
            raise LLMConnectionError(f"Aplikacja kliencka {self.client_id} nie odebrała komendy chat_stream.")

        try:
            while True:
                ev = await asyncio.wait_for(task_queue.get(), timeout=120.0)
                ev_type = ev.get("type")

                if ev_type == "content":
                    yield {"type": "content", "content": ev.get("content", "")}
                elif ev_type == "profiler":
                    yield ev
                elif ev_type == "error":
                    raise LLMConnectionError(ev.get("content", "Błąd usługi aplikacji klienckiej"))
                elif ev_type == "done":
                    tool_calls = ev.get("tool_calls")
                    if tool_calls:
                        yield {"type": "tool_calls", "tool_calls": tool_calls}
                    break
        finally:
            _pending_tasks.pop(task_id, None)
