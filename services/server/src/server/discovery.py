"""Rozgłasza obecność serwera w sieci lokalnej (UDP broadcast) — pozwala
satelitom (`services/desktop_satellite/`) znaleźć adres serwera bez ręcznej
konfiguracji IP w każdej z nich. Kontrakt payloadu żyje w
`shared.discovery` (współdzielony z klientem).

Startuje zawsze razem z serwerem, bez osobnego przełącznika `enabled` —
zgodnie z zasadą przyjętą w projekcie dla usług domenowych (`docs/manifest.md`,
sekcja 5): albo działa, albo nie jest uruchomiona.
"""

from __future__ import annotations

import asyncio
import socket

from shared import DISCOVERY_UDP_PORT, encode_beacon, get_logger

logger = get_logger("regis.discovery")


class DiscoveryBroadcaster:
    """Cyklicznie wysyła beacon UDP broadcast z portem serwera."""

    def __init__(self, port: int, interval_seconds: float = 5.0) -> None:
        self._port = port
        self._interval_seconds = interval_seconds
        self._sock: socket.socket | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._task = asyncio.create_task(self._broadcast_loop())
        logger.info(f"Rozgłaszanie obecności serwera uruchomione [port UDP: {DISCOVERY_UDP_PORT}].")

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        logger.info("Rozgłaszanie obecności serwera zatrzymane.")

    async def _broadcast_loop(self) -> None:
        assert self._sock is not None
        beacon = encode_beacon(self._port)
        while True:
            try:
                self._sock.sendto(beacon, ("<broadcast>", DISCOVERY_UDP_PORT))
            except OSError as err:
                logger.warning(f"Nie udało się rozgłosić obecności serwera: {err}")
            await asyncio.sleep(self._interval_seconds)
