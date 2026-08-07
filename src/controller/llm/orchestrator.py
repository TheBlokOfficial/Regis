"""
Orkiestrator Konwersacji Regis.

Cienka fasada routingowa — odpowiednik ws_dispatcher w module klienta.
Decyduje który pipeline uruchomić (cloud lub worker) i deleguje wykonanie.
Logika wykonania, zapis historii i publikacja EventBus są w llm/pipeline/.
"""
import asyncio
import logging

import requests

import controller.core.app_state as app_state
import controller.core.client_store as client_store
import controller.core.session_store as session_store
import controller.llm.providers as providers
from controller.llm.backends.ollama import OllamaBackend
from controller.llm.pipeline.cloud import run_cloud_pipeline
from controller.llm.pipeline.worker import run_worker_pipeline

logger = logging.getLogger(__name__)


async def proxy_sse_to_queue(
    base_payload: dict,
    q: asyncio.Queue,
    is_audio: bool = False,
    audio_bytes: bytes = None,
) -> None:
    """
    Punkt wejścia orkiestratora — wybiera pipeline i deleguje wykonanie.

    Args:
        base_payload: Słownik żądania (message, room, satellite_id, controller_url).
        q: Kolejka eventów SSE — pipeline wrzuca tu tokeny i statusy.
        is_audio: True jeśli żądanie pochodzi z wejścia audio.
        audio_bytes: Surowe bajty audio WAV (tylko gdy is_audio=True).
    """
    loop = asyncio.get_event_loop()

    backend = providers.get_llm_backend()
    if backend is None:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Brak dostępnego providera LLM."})
        return

    satellite_id = base_payload.get("satellite_id") or "web_ui"
    session_history = session_store.get_session_history(satellite_id)

    use_cloud = not is_audio and not isinstance(backend, OllamaBackend)

    if use_cloud:
        try:
            await run_cloud_pipeline(
                payload=base_payload,
                backend=backend,
                session_history=session_history,
                q=q,
                loop=loop,
            )
        except Exception:
            # Fallback na worker przy błędzie chmury
            logger.warning("Cloud pipeline zawiódł — próba fallbacku na węzeł lokalny.")
            await _run_worker_or_error(base_payload, session_history, q, loop, is_audio, audio_bytes)
    else:
        await _run_worker_or_error(base_payload, session_history, q, loop, is_audio, audio_bytes)


async def _run_worker_or_error(
    payload: dict,
    session_history: list[dict],
    q: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    is_audio: bool,
    audio_bytes: bytes | None,
) -> None:
    """Wybiera najlepszy węzeł LLM i uruchamia worker pipeline. Zwraca błąd jeśli brak węzłów."""
    llm_nodes = client_store.get_llm_clients()
    if not llm_nodes:
        loop.call_soon_threadsafe(q.put_nowait, {"type": "error", "content": "Brak dostępnej usługi LLM."})
        return

    llm_node = sorted(llm_nodes, key=lambda w: w.get("priority", 10), reverse=True)[0]

    await run_worker_pipeline(
        payload=payload,
        llm_node=llm_node,
        session_history=session_history,
        q=q,
        loop=loop,
        is_audio=is_audio,
        audio_bytes=audio_bytes,
    )


def clear_conversation_history(satellite_id: str | None = None) -> None:
    """Resetuje historię konwersacji w pamięci Kontrolera oraz powiązanych węzłach."""
    session_store.clear_session_history(satellite_id)

    for worker in client_store.get_llm_clients():
        try:
            requests.post(f"{worker['base_url']}/v1/clear_history", timeout=2)
        except Exception:
            pass
