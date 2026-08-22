"""Punkt wejścia satelity desktopowej — długo działający proces konsolowy z pętlą
reconnect (backoff), czystym zamknięciem mikrofonu na Ctrl+C i logowaniem przez
wspólny helper `shared.get_logger` (konwencja `AGENTS.md`).

`--sender-id`/`--server-url` są opcjonalne: bez `--sender-id` satelita używa
trwałego UUID4 z `config/settings.json` (tworzonego przy pierwszym
uruchomieniu, patrz `desktop_satellite.config`); bez `--server-url` przed
każdą próbą połączenia szuka serwera przez UDP broadcast auto-discovery
(`desktop_satellite.discovery`).
"""

from __future__ import annotations

import argparse
import asyncio

from shared import get_logger, setup_logging

from desktop_satellite.audio import FRAME_DURATION_MS, MicCapture, SpeakerPlayback
from desktop_satellite.config import load_or_create_sender_id
from desktop_satellite.discovery import discover_server
from desktop_satellite.protocol_client import ProtocolClient
from desktop_satellite.session import SatelliteSession
from desktop_satellite.vad import SilenceVadDetector

logger = get_logger("regis.desktop_satellite.main")

RECONNECT_DELAY_SECONDS = 3.0
DISCOVERY_TIMEOUT_SECONDS = 15.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Satelita desktopowa Regis (Windows/Linux).")
    parser.add_argument(
        "--server-url",
        default=None,
        help="WS bazowy adres serwera (np. ws://192.168.1.10:8000/ws/voice). Pominięcie włącza auto-discovery UDP.",
    )
    parser.add_argument(
        "--sender-id",
        default=None,
        help="Opaque sender_id tej satelity. Pominięcie użyje/utworzy trwały UUID w config/settings.json.",
    )
    parser.add_argument("--log-level", default="INFO", help="Poziom logowania (domyślnie INFO).")
    return parser.parse_args()


async def run_forever(server_url_override: str | None, sender_id: str) -> None:
    mic = MicCapture()
    speaker = SpeakerPlayback()
    while True:
        server_url = server_url_override or await discover_server(DISCOVERY_TIMEOUT_SECONDS)
        if server_url is None:
            logger.warning(f"Serwer nie znaleziony (auto-discovery). Ponowna próba za {RECONNECT_DELAY_SECONDS:.0f}s.")
            await asyncio.sleep(RECONNECT_DELAY_SECONDS)
            continue

        def vad_factory(silence_duration_ms: float, amplitude_threshold: int) -> SilenceVadDetector:
            return SilenceVadDetector(
                frame_duration_ms=FRAME_DURATION_MS,
                silence_duration_ms=silence_duration_ms,
                amplitude_threshold=amplitude_threshold,
            )

        link = ProtocolClient(server_url, sender_id)
        try:
            logger.info(f"Łączenie z serwerem [{server_url}, sender_id: '{sender_id}'] ...")
            await link.connect()
            mic.start()
            session = SatelliteSession(link=link, speaker=speaker, vad_factory=vad_factory)
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

    if args.sender_id:
        sender_id = args.sender_id
        logger.info(f"sender_id: '{sender_id}' (z flagi --sender-id).")
    else:
        sender_id = load_or_create_sender_id()
        logger.info(f"sender_id: '{sender_id}' (z config/settings.json).")

    try:
        asyncio.run(run_forever(args.server_url, sender_id))
    except KeyboardInterrupt:
        logger.info("Zatrzymano (Ctrl+C).")


if __name__ == "__main__":
    main()
