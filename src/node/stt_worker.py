import asyncio
import json
import logging
import os
import re

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from node.engines.stt_engine import STTEngine
from core import config

# Regex został usunięty, ponieważ przechodzimy na inteligentne filtrowanie po czasie (timestampach)!
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

app = FastAPI()
stt_engine = None

@app.on_event("startup")
async def startup_event():
    global stt_engine
    logging.info("Inicjalizacja silnika STT Vosk...")
    stt_engine = STTEngine(model_size="small")

@app.get("/v1/health")
async def health():
    return {"status": "ok", "service": "stt-worker"}

@app.websocket("/v1/stt/stream")
async def stt_stream(websocket: WebSocket):
    await websocket.accept()
    if not stt_engine:
        await websocket.send_json({"type": "error", "content": "STT Engine not initialized."})
        await websocket.close()
        return

    rec = stt_engine.create_recognizer()
    rec.SetWords(True)
    results = []
    partial_text = ""

    try:
        while True:
            msg = await websocket.receive()
            if "bytes" in msg:
                data = msg["bytes"]
                if data == b"EOF":
                    break
                
                if rec.AcceptWaveform(data):
                    part = json.loads(rec.Result())
                    if "result" in part:
                        # Bufor pre-rekordu kończy się dokładnie na 3.0s. 
                        # Słowo wybudzające kończy się zazwyczaj między 2.9s a 3.1s.
                        # Próg 3.2s gwarantuje usunięcie słowa wybudzającego i ewentualnych szumów,
                        # podczas gdy pierwsza część komendy (np. "zgaś") kończy się najwcześniej ok. 3.5s.
                        words = [w["word"] for w in part["result"] if w.get("end", 0) > 3.2]
                        if words:
                            results.append(" ".join(words))
                    elif "text" in part and part["text"]:
                        results.append(part["text"])
                    partial_text = ""
                else:
                    part = json.loads(rec.PartialResult())
                    if "partial_result" in part:
                        words = [w["word"] for w in part["partial_result"] if w.get("end", 0) > 3.2]
                        partial_text = " ".join(words)
                    else:
                        partial_text = part.get("partial", "")
                        
                current_text = (" ".join(results) + " " + partial_text).strip()
                if current_text:
                    await websocket.send_json({"type": "stt_partial", "content": current_text})
            elif "text" in msg:
                pass
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logging.error(f"Błąd STT: {e}")
        
    try:
        part = json.loads(rec.FinalResult())
        if "result" in part:
            words = [w["word"] for w in part["result"] if w.get("end", 0) > 3.2]
            if words:
                results.append(" ".join(words))
        elif "text" in part and part["text"]:
            results.append(part["text"])
            
        final_text = " ".join(results).strip()
        if final_text:
            await websocket.send_json({"type": "stt_result", "content": final_text})
        else:
            await websocket.send_json({"type": "error", "content": "Nie rozpoznano żadnego tekstu ze strumienia audio."})
    except Exception:
        pass
        
    try:
        await websocket.close()
    except Exception:
        pass

def start():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

if __name__ == "__main__":
    start()
