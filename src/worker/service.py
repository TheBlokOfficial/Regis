import asyncio
import json
import logging
import threading

from worker.node import WorkerNode
from worker.remote_tools_registry import RemoteToolsRegistry

logger = logging.getLogger(__name__)


class WorkerInferenceService:
    """Zarządza instancją WorkerNode, uruchamianiem inferencji w wątkach oraz przekazywaniem zdarzeń do SSE."""

    def __init__(self):
        self.worker_node: WorkerNode | None = None

    def initialize(self, model_name: str, temperature: float, history_limit: int):
        self.worker_node = WorkerNode(
            model_name=model_name,
            temperature=temperature,
            history_limit=history_limit
        )

    def shutdown(self):
        if self.worker_node:
            self.worker_node.unload_model()
            self.worker_node = None

    async def stream_events(self, q: asyncio.Queue):
        """Generator Server-Sent Events czytający z kolejki zdarzeń."""
        while True:
            item = await q.get()
            yield f"data: {json.dumps(item)}\n\n"
            if item["type"] in ("done", "error"):
                break

    def run_chat_stream(
        self,
        message: str,
        system_prompt: str,
        history: list[dict],
        controller_url: str,
        room: str | None,
        q: asyncio.Queue,
        loop: asyncio.AbstractEventLoop
    ):
        remote_tools = RemoteToolsRegistry(controller_url, room=room)

        def run_inference():
            from worker.history_utils import build_messages_from_history
            try:
                messages = build_messages_from_history(
                    system_prompt=system_prompt,
                    history=history,
                    current_message=message
                )
                response_text = self.worker_node.handle_chat(
                    messages,
                    remote_tools,
                    on_tool_call=lambda msg: loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": msg}),
                    on_thought_token=lambda chunk: loop.call_soon_threadsafe(q.put_nowait, {"type": "thought", "content": chunk}),
                    on_content_token=lambda chunk: loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": chunk}),
                    on_raw_tool_call=lambda data: loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_dict", "content": data})
                )
                loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": response_text})
            except Exception as e:
                logger.exception("Błąd generacji odpowiedzi")
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})

        threading.Thread(target=run_inference).start()

    def run_audio_stream(
        self,
        audio_bytes: bytes,
        system_prompt: str,
        history_json: str,
        controller_url: str,
        q: asyncio.Queue,
        loop: asyncio.AbstractEventLoop
    ):
        remote_tools = RemoteToolsRegistry(controller_url, room=None)

        def run_inference():
            try:
                parsed_history = json.loads(history_json)
                response_text = self.worker_node.handle_audio(
                    audio_bytes,
                    remote_tools,
                    system_prompt=system_prompt,
                    history=parsed_history,
                    on_stt_result=lambda text: loop.call_soon_threadsafe(q.put_nowait, {"type": "stt_result", "content": text}),
                    on_tool_call=lambda msg: loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_call_raw", "content": msg}),
                    on_thought_token=lambda chunk: loop.call_soon_threadsafe(q.put_nowait, {"type": "thought", "content": chunk}),
                    on_content_token=lambda chunk: loop.call_soon_threadsafe(q.put_nowait, {"type": "content", "content": chunk}),
                    on_raw_tool_call=lambda data: loop.call_soon_threadsafe(q.put_nowait, {"type": "tool_dict", "content": data})
                )
                if response_text == "Nie rozpoznano żadnego tekstu ze strumienia audio.":
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": response_text})
                else:
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "done", "content": response_text})
            except Exception as e:
                logger.exception("Błąd generacji odpowiedzi z audio")
                loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})

        threading.Thread(target=run_inference).start()

    def clear_history(self):
        if self.worker_node:
            self.worker_node.clear_history()


inference_service = WorkerInferenceService()
