"""
Usługa komunikacji ze zmysłami Audio (STT / TTS).

Odpowiada za niskopoziomowe połączenia HTTP z dostępnymi usługami audio (transkrypcję mowy i syntezę mowy).
"""
import asyncio
import logging
import time

import requests

import controller.core.client_store as client_store

logger = logging.getLogger(__name__)


async def transcribe_audio(audio_bytes: bytes) -> tuple[str | None, int]:
    """
    Wysyła surowe bajty audio do pierwszego dostępnego serwisu STT i zwraca rozpoznany tekst oraz czas ms.

    Returns:
        tuple[tekst_lub_None, czas_w_ms]
    """
    stt_nodes = client_store.get_audio_clients()
    if not stt_nodes:
        logger.warning("Brak dostępnej usługi STT.")
        return None, 0

    stt_node = stt_nodes[0]
    stt_url = f"{stt_node['base_url']}/v1/stt/transcribe"
    t_start = time.time()

    try:
        files = {"file": ("audio.wav", audio_bytes, "audio/wav")}
        stt_resp = await asyncio.to_thread(requests.post, stt_url, files=files, timeout=(1.0, 30.0))
        stt_resp.raise_for_status()
        stt_json = stt_resp.json()
        stt_content = stt_json.get("text", "")
        stt_ms = stt_json.get("elapsed_ms") or int((time.time() - t_start) * 1000)

        if not stt_content:
            logger.warning("Usługa STT nie rozpoznała żadnego tekstu z nagrania.")
            return None, stt_ms

        return stt_content, stt_ms
    except Exception as e:
        logger.exception(f"Błąd komunikacji z usługą STT: {e}")
        return None, int((time.time() - t_start) * 1000)


async def synthesize_speech(text: str) -> tuple[str | None, int]:
    """
    Wysyła tekst do pierwszego dostępnego serwisu TTS i zwraca bajty audio w base64 oraz czas ms.

    Returns:
        tuple[audio_b64_lub_None, czas_w_ms]
    """
    tts_nodes = client_store.get_audio_clients()
    if not tts_nodes:
        logger.debug("Brak dostępnej usługi TTS.")
        return None, 0

    tts_node = tts_nodes[0]
    tts_url = f"{tts_node['base_url']}/v1/tts/synthesize"
    t_start = time.time()

    try:
        tts_resp = await asyncio.to_thread(
            requests.post, tts_url,
            json={"text": text},
            timeout=(1.0, 30.0),
        )
        if tts_resp.ok:
            tts_json = tts_resp.json()
            b64_audio = tts_json.get("audio_b64")
            tts_ms = tts_json.get("elapsed_ms") or int((time.time() - t_start) * 1000)
            return b64_audio, tts_ms

        logger.warning(f"Usługa TTS zwróciła kod odpowiedzi {tts_resp.status_code}")
        return None, int((time.time() - t_start) * 1000)
    except Exception as e:
        logger.warning(f"Błąd usługi TTS: {e}")
        return None, int((time.time() - t_start) * 1000)
