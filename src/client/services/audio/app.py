"""
Endpointy API usługi Audio (STT Whisper + TTS Piper).
"""
import io
import time
import asyncio
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import client.services.audio.__main__ as audio_main

app = FastAPI(lifespan=audio_main.lifespan)


class TTSSynthesizeRequest(BaseModel):
    text: str


@app.get("/v1/health")
async def health():
    return {
        "status": "ok",
        "service": "audio",
        "node_id": audio_main.service_instance.node_id,
        "stt_model_size": audio_main.service_instance.stt_model_size,
        "tts_model_name": audio_main.service_instance.tts_model_name
    }


@app.post("/v1/stt/transcribe")
async def transcribe(file: UploadFile = File(...)):
    """Transkrybuje przesłany plik audio WAV na tekst (STT)."""
    _start = time.perf_counter()
    audio_bytes = await file.read()
    audio_io = io.BytesIO(audio_bytes)

    if audio_main.service_instance.stt_engine is None:
        from client.engines.stt_engine import STTEngine
        audio_main.service_instance.stt_engine = STTEngine(model_size=audio_main.service_instance.stt_model_size, language="pl")

    try:
        text = await asyncio.to_thread(audio_main.service_instance.stt_engine.transcribe_audio_file, audio_io)
        elapsed_ms = int((time.perf_counter() - _start) * 1000)
        return {
            "text": text or "",
            "elapsed_ms": elapsed_ms
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Błąd transkrypcji STT: {e}"})


@app.post("/v1/tts/synthesize")
async def synthesize(request: TTSSynthesizeRequest):
    """Syntezuje podany tekst na mowę (audio base64 WAV - TTS)."""
    _start = time.perf_counter()

    if not request.text or not request.text.strip():
        return {"audio_b64": "", "elapsed_ms": 0}

    if audio_main.service_instance.tts_engine is None:
        from client.engines.tts_engine import TTSEngine
        audio_main.service_instance.tts_engine = TTSEngine(model_name=audio_main.service_instance.tts_model_name)

    try:
        b64_audio = await asyncio.to_thread(audio_main.service_instance.tts_engine.synthesize_to_base64, request.text)
        elapsed_ms = int((time.perf_counter() - _start) * 1000)
        return {
            "audio_b64": b64_audio or "",
            "elapsed_ms": elapsed_ms
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Błąd syntezy TTS: {e}"})
