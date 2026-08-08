"""
Orkiestrator Konwersacji Regis (Warstwa 1 – Core).

Czysta fasada wysokiego poziomu — koordynuje przepływ tury:
wywołuje transkrypcję audio, pobiera backend LLM, odpala silnik agenta oraz generuje syntezę mowy.
"""
import asyncio
import logging

import controller.core.session.store as session_store
import controller.providers.llm.resolver as providers
from controller.providers.audio.service import transcribe_audio, synthesize_speech
from controller.agent.engine import run_agent_loop

logger = logging.getLogger(__name__)


async def execute_interaction_turn(
    base_payload: dict,
    q: asyncio.Queue,
    is_audio: bool = False,
    audio_bytes: bytes | None = None,
) -> None:
    """
    Główny punkt wejścia Orkiestratora — wykonuje pełną turę interakcji:
    zarządza wejściem STT, wybiera najlepszy backend LLM, odpala pętlę agenta oraz generuje wyjście TTS.
    """
    loop = asyncio.get_event_loop()

    backend = providers.get_llm_backend()
    if backend is None:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Brak dostępnego providera LLM."})
        return

    # 1. Krok Wejścia Audio (STT)
    if is_audio and audio_bytes:
        stt_text, stt_ms = await transcribe_audio(audio_bytes)
        if stt_ms > 0:
            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "profiler", 
                "content": {"metric": "stt", "value": stt_ms}
            })

        if not stt_text:
            loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Nie rozpoznano tekstu ze strumienia audio."})
            return

        loop.call_soon_threadsafe(q.put_nowait, {"type": "stt_result", "content": stt_text})
        base_payload["message"] = stt_text

    satellite_id = base_payload.get("satellite_id") or "web_ui"
    room = base_payload.get("room")
    user_message = base_payload.get("message", "")
    session_history = session_store.get_session_history(satellite_id)
    provider_name = backend.get_provider_name()
    model_name = getattr(backend, "model_name", "nieznany")

    loop.call_soon_threadsafe(q.put_nowait, {
        "type": "routing_info",
        "worker_id": provider_name,
        "model": model_name,
        "provider": provider_name,
    })

    # 2. Krok Przetwarzania LLM (Silnik ReAct)
    try:
        final_content = await run_agent_loop(
            stream_provider=backend,
            session_history=session_history,
            user_message=user_message,
            satellite_id=satellite_id,
            room=room,
            worker_id=provider_name,
            model_name=model_name,
            q=q,
            loop=loop,
        )
    except Exception as e:
        logger.exception(f"Błąd w pętli orkiestratora: {e}")
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": str(e)})
        raise

    # 3. Krok Wyjścia Audio (TTS)
    if is_audio and final_content:
        b64_audio, tts_ms = await synthesize_speech(final_content)
        if tts_ms > 0:
            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "profiler", 
                "content": {"metric": "tts", "value": tts_ms}
            })
        if b64_audio:
            loop.call_soon_threadsafe(q.put_nowait, {"type": "tts_audio", "content": b64_audio})
