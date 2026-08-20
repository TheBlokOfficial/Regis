"""Auto-discovery serwera — nasłuchuje UDP broadcast rozgłaszanego przez
`server.discovery.DiscoveryBroadcaster`, żeby nie trzeba było ręcznie wpisywać
adresu IP serwera. Kontrakt payloadu żyje w `shared.discovery`.
"""

from __future__ import annotations

import asyncio
import socket

from shared import DISCOVERY_UDP_PORT, decode_beacon, get_logger

logger = get_logger("regis.desktop_satellite.discovery")


def select_server_url(beacon_port: int, source_ip: str) -> str:
    """Buduje bazowy adres WS z portu ogłoszonego w beaconie i adresu nadawcy pakietu."""
    return f"ws://{source_ip}:{beacon_port}/ws/voice"


async def discover_server(timeout_seconds: float = 15.0) -> str | None:
    """Nasłuchuje broadcastu UDP serwera; `None` po przekroczeniu timeoutu.
    Blokujące gniazdo wykonywane w wątku wykonawczym, żeby nie blokować pętli asyncio."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _listen_blocking, timeout_seconds)


def _listen_blocking(timeout_seconds: float) -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(timeout_seconds)
    try:
        sock.bind(("", DISCOVERY_UDP_PORT))
        while True:
            raw, (source_ip, _source_port) = sock.recvfrom(1024)
            port = decode_beacon(raw)
            if port is not None:
                return select_server_url(port, source_ip)
    except socket.timeout:
        return None
    except OSError as err:
        logger.warning(f"Nasłuch UDP discovery nieudany: {err}")
        return None
    finally:
        sock.close()
