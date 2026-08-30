"""Obsługuje discovery w LAN: odpowiada unicastem na aktywne zapytania satelit
i zachowuje cykliczny UDP broadcast dla starszych klientów. Pozwala to znaleźć
serwer bez ręcznej konfiguracji IP. Kontrakt payloadu żyje w
`shared.discovery` (współdzielony z klientem).

Startuje zawsze razem z serwerem, bez osobnego przełącznika `enabled` —
zgodnie z zasadą przyjętą w projekcie dla usług domenowych (`docs/manifest.md`,
sekcja 5): albo działa, albo nie jest uruchomiona.
"""

from __future__ import annotations

import asyncio
import socket

from shared import DISCOVERY_UDP_PORT, encode_beacon, get_logger, is_discovery_query

logger = get_logger("regis.discovery")


class DiscoveryBroadcaster:
    """Cyklicznie wysyła beacon UDP broadcast z portem serwera."""

    def __init__(self, port: int, interval_seconds: float = 5.0) -> None:
        self._port = port
        self._interval_seconds = interval_seconds
        self._sock: socket.socket | None = None
        self._tasks: list[asyncio.Task[None]] = []

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.bind(("", DISCOVERY_UDP_PORT))
        self._sock.setblocking(False)
        self._tasks = [
            asyncio.create_task(self._broadcast_loop()),
            asyncio.create_task(self._response_loop()),
        ]
        logger.info(f"UDP discovery uruchomione [port: {DISCOVERY_UDP_PORT}].")

    def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        logger.info("Rozgłaszanie obecności serwera zatrzymane.")

    async def _broadcast_loop(self) -> None:
        assert self._sock is not None
        loop = asyncio.get_running_loop()
        beacon = encode_beacon(self._port)
        while True:
            try:
                await loop.sock_sendto(self._sock, beacon, ("<broadcast>", DISCOVERY_UDP_PORT))
            except OSError as err:
                logger.warning(f"Nie udało się rozgłosić obecności serwera: {err}")
            await asyncio.sleep(self._interval_seconds)

    async def _response_loop(self) -> None:
        """Odpowiada unicastem na aktywne zapytania klientów.

        Odpowiedź na ruch zainicjowany przez satelitę przechodzi przez stanową zaporę
        Windows, w przeciwieństwie do niezamówionego pasywnego broadcastu.
        """
        assert self._sock is not None
        loop = asyncio.get_running_loop()
        beacon = encode_beacon(self._port)
        while True:
            raw, source = await loop.sock_recvfrom(self._sock, 1024)
            if is_discovery_query(raw):
                await loop.sock_sendto(self._sock, beacon, source)
