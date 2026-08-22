"""Symulator satelity głosowej — łączy się z `/ws/voice/{sender_id}` i przechodzi cały
cykl protokołu (handshake -> wake-word -> nagrywanie -> utterance_end -> odbiór TTS)
bez żadnego prawdziwego sprzętu, mikrofonu ani modelu wake-word.

Wymaga uruchomionego serwera (`python -m uv run --package server python -m server.main`),
domyślnie łączy się z `ws://127.0.0.1:8000/ws/voice/<sender_id>`.

Użycie:
    python services/server/scripts/voice_satellite_sim.py [sender_id]
"""

from __future__ import annotations

import asyncio
import json
import sys

import websockets

DEFAULT_URL = "ws://127.0.0.1:8000/ws/voice"
# Dowolna, wystarczająco "głośna" ramka PCM16 mono, żeby przekroczyć próg
# ThresholdEnergyWakeWordDetector (patrz server/voice/wakeword.py) — placeholder
# do czasu podłączenia realnego modelu .onnx.
_LOUD_FRAME = (30000).to_bytes(2, byteorder="little", signed=True) * 160  # ~10ms przy 16kHz
_QUIET_FRAME = (10).to_bytes(2, byteorder="little", signed=True) * 160


async def _expect_control(ws, expected_type: str) -> None:
    raw = await ws.recv()
    if isinstance(raw, bytes):
        raise AssertionError(f"Oczekiwano ramki kontrolnej JSON, dostano {len(raw)} bajtów binarnych.")
    message = json.loads(raw)
    print(f"<- {message}")
    assert message.get("type") == expected_type, f"Oczekiwano '{expected_type}', dostano '{message.get('type')}'."


async def run(sender_id: str) -> None:
    url = f"{DEFAULT_URL}/{sender_id}"
    print(f"Łączenie z {url} ...")
    async with websockets.connect(url) as ws:
        # 1. Handshake możliwości
        hello = {"type": "hello", "capabilities": ["mic", "speaker"]}
        print(f"-> {hello}")
        await ws.send(json.dumps(hello))
        await _expect_control(ws, "client_config")

        # 2. Kilka cichych ramek (nie powinny wywołać wake_detected)
        for _ in range(3):
            await ws.send(_QUIET_FRAME)

        # 3. Głośne ramki -> wake-word wykryty (ThresholdEnergyWakeWordDetector, domyślnie 3 kolejne)
        for _ in range(3):
            await ws.send(_LOUD_FRAME)
        await _expect_control(ws, "wake_detected")

        # 4. Symulacja nagranej wypowiedzi
        for _ in range(5):
            await ws.send(_LOUD_FRAME)

        # 5. Koniec wypowiedzi (satelita: własny VAD wykrył ciszę)
        utterance_end = {"type": "utterance_end"}
        print(f"-> {utterance_end}")
        await ws.send(json.dumps(utterance_end))
        await _expect_control(ws, "play_stop_tone")

        # 6. Odbiór odpowiedzi: tts_start -> ramki binarne -> tts_end
        await _expect_control(ws, "tts_start")
        audio_bytes = 0
        while True:
            raw = await ws.recv()
            if isinstance(raw, bytes):
                audio_bytes += len(raw)
                continue
            message = json.loads(raw)
            print(f"<- {message}")
            assert message.get("type") == "tts_end"
            break
        print(f"Odebrano {audio_bytes} bajtów audio odpowiedzi.")

        # 7. Potwierdzenie zakończenia odtwarzania — powrót do nasłuchu
        playback_done = {"type": "playback_done"}
        print(f"-> {playback_done}")
        await ws.send(json.dumps(playback_done))

    print("Cykl zakończony pomyślnie.")


if __name__ == "__main__":
    sender_id = sys.argv[1] if len(sys.argv) > 1 else "sim_satellite_1"
    asyncio.run(run(sender_id))
