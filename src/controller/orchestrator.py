"""
Orkiestrator Konwersacji Regis (Warstwa 1 – Core).

Jednolity koordynator tury konwersacji (tekstowej lub głosowej).
Przyjmuje intencje tekstowe/głosowe od nadawcy (sender) i przekazuje je do
jednolitego strumienia wykonawczego _execute_turn_stream (ReAct + TTS).
"""
import asyncio
import logging
from typing import AsyncGenerator

import controller.agent.session.store as session_store
import controller.core.client_registry as client_registry
import controller.core.state as app_state
import controller.providers.llm.resolver as providers
from controller.config.loader import get_controller_url
from controller.providers.audio.service import transcribe_audio, synthesize_speech
from controller.agent.engine import run_agent_loop

logger = logging.getLogger(__name__)


async def handle_text_message(
    text: str,
    sender: str = "web_ui",
) -> AsyncGenerator[dict, None]:
    """
    Publiczne wejście dla przychodzącej wiadomości tekstowej.
    Przekazuje treść i nadawcę bezpośrednio do strumienia wykonawczego.
    """
    async for event in _execute_turn_stream(text=text, sender=sender, is_audio=False):
        yield event


async def handle_audio_message(
    audio_bytes: bytes,
    sender: str = "web_ui",
) -> AsyncGenerator[dict, None]:
    """
    Publiczne wejście dla przychodzącej wiadomości głosowej.
    Sprawdza obecność audio, wykonuje STT i przekazuje wytranskrybowany tekst do strumienia.
    """
    if not audio_bytes:
        yield {"type": "error", "content": "Przesłany strumień audio jest pusty."}
        return

    stt_text, stt_ms = await transcribe_audio(audio_bytes)

    if stt_ms > 0:
        yield {
            "type": "profiler", 
            "content": {"metric": "stt", "value": stt_ms}
        }

    if not stt_text:
        yield {"type": "error", "content": "Nie rozpoznano tekstu ze strumienia audio."}
        return

    yield {"type": "stt_result", "content": stt_text}

    async for event in _execute_turn_stream(text=stt_text, sender=sender, is_audio=True):
        yield event


async def _execute_turn_stream(
    text: str,
    sender: str,
    is_audio: bool,
) -> AsyncGenerator[dict, None]:
    """
    Prywatna logika wykonawcza: pobiera pokój nadawcy, weryfikuje obecność LLM,
    uruchamia pętlę ReAct silnika agenta oraz opcjonalnie wykonuje syntezę mowy (TTS).
    """
    if not providers.has_llm_provider():
        yield {"type": "error", "content": "Brak dostępnego providera LLM."}
        return

    backend = providers.get_llm_backend()
    if backend is None:
        yield {"type": "error", "content": "Brak dostępnego providera LLM."}
        return

    room = client_registry.get_client_room(sender)
    session_history = session_store.get_session_history(sender)
    provider_name = backend.get_provider_name()
    model_name = getattr(backend, "model_name", "nieznany")

    yield {
        "type": "routing_info",
        "worker_id": provider_name,
        "model": model_name,
        "provider": provider_name,
    }

    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # Krok Przetwarzania LLM (Mózg Agenta ReAct)
    async def _runner():
        try:
            final_content = await run_agent_loop(
                stream_provider=backend,
                session_history=session_history,
                user_message=text or "",
                satellite_id=sender,
                room=room,
                worker_id=provider_name,
                model_name=model_name,
                q=q,
                loop=loop,
                tools_registry=app_state.tools_registry,
            )

            if is_audio and final_content:
                b64_audio, tts_ms = await synthesize_speech(final_content)
                if tts_ms > 0:
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "type": "profiler", 
                        "content": {"metric": "tts", "value": tts_ms}
                    })
                if b64_audio:
                    loop.call_soon_threadsafe(q.put_nowait, {"type": "tts_audio", "content": b64_audio})

        except Exception as e:
            logger.exception(f"Błąd w pętli orkiestratora: {e}")
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})

    task = asyncio.create_task(_runner())

    while True:
        item = await q.get()
        yield item
        if item["type"] in ("done", "error"):
            break

    await task


# Rejestracja handlerów w Agnostycznej Magistrali Wiadomości (MessageBus)
from controller.core.message_bus import message_bus
from controller.messages import TextMessage, AudioMessage


async def _on_text_message(msg: TextMessage) -> AsyncGenerator[dict, None]:
    async for event in handle_text_message(msg.text, msg.sender):
        yield event


async def _on_audio_message(msg: AudioMessage) -> AsyncGenerator[dict, None]:
    async for event in handle_audio_message(msg.audio_bytes, msg.sender):
        yield event


message_bus.subscribe(TextMessage, _on_text_message)
message_bus.subscribe(AudioMessage, _on_audio_message)
