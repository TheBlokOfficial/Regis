"""Punkt wejścia satelity desktopowej — długo działający proces konsolowy z pętlą
reconnect (backoff), czystym zamknięciem mikrofonu na Ctrl+C i logowaniem przez
wspólny helper `shared.get_logger` (konwencja `AGENTS.md`).
"""

from __future__ import annotations

import argparse
import asyncio

from shared import get_logger, setup_logging

from desktop_satellite.audio import FRAME_DURATION_MS, MicCapture, SpeakerPlayback
from desktop_satellite.protocol_client import ProtocolClient
from desktop_satellite.session import SatelliteSession
from desktop_satellite.vad import SilenceVadDetector

logger = get_logger("regis.desktop_satellite.main")

DEFAULT_SERVER_URL = "ws://127.0.0.1:8000/ws/voice"
RECONNECT_DELAY_SECONDS = 3.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Satelita desktopowa Regis (Windows/Linux).")
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL, help=f"WS bazowy adres (domyślnie {DEFAULT_SERVER_URL}).")
    parser.add_argument("--sender-id", required=True, help="Opaque sender_id tej satelity (patrz Web UI: Świat -> Nadawcy).")
    parser.add_argument("--log-level", default="INFO", help="Poziom logowania (domyślnie INFO).")
    return parser.parse_args()


async def run_forever(server_url: str, sender_id: str) -> None:
    mic = MicCapture()
    speaker = SpeakerPlayback()
    while True:
        vad = SilenceVadDetector(frame_duration_ms=FRAME_DURATION_MS)
        link = ProtocolClient(server_url, sender_id)
        try:
            logger.info(f"Łączenie z serwerem [sender_id: '{sender_id}'] ...")
            await link.connect()
            mic.start()
            session = SatelliteSession(link=link, speaker=speaker, vad=vad)
            await session.run(mic)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # połączenie padło/serwer nieosiągalny — reconnect
            logger.warning(f"Połączenie przerwane: {err}. Ponowna próba za {RECONNECT_DELAY_SECONDS:.0f}s.")
        finally:
            mic.stop()
            await link.close()
        await asyncio.sleep(RECONNECT_DELAY_SECONDS)


def main() -> None:
    args = parse_args()
    setup_logging(args.log_level)
    try:
        asyncio.run(run_forever(args.server_url, args.sender_id))
    except KeyboardInterrupt:
        logger.info("Zatrzymano (Ctrl+C).")


if __name__ == "__main__":
    main()
