"""Auto-discovery serwera — pyta broadcastem przez każdy interfejs IPv4 i odbiera
odpowiedź unicast od `server.discovery.DiscoveryBroadcaster`, żeby nie trzeba było
ręcznie wpisywać adresu IP. Kontrakt payloadu żyje w `shared.discovery`.
"""

from __future__ import annotations

import asyncio
import select
import socket
import time

from shared import DISCOVERY_UDP_PORT, decode_beacon, encode_discovery_query, get_logger

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
    sockets = _open_interface_sockets()
    if not sockets:
        logger.warning("Brak lokalnego interfejsu IPv4 do auto-discovery.")
        return None
    try:
        deadline = time.monotonic() + timeout_seconds
        next_query_at = 0.0
        query = encode_discovery_query()
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_query_at:
                for sock in sockets:
                    try:
                        sock.sendto(query, ("<broadcast>", DISCOVERY_UDP_PORT))
                    except OSError as err:
                        # Jeden martwy interfejs (np. rozłączony VPN) nie może blokować
                        # pozostałych, przez które serwer może być osiągalny.
                        logger.debug(f"Zapytanie discovery nie wyszło przez {sock.getsockname()[0]}: {err}")
                next_query_at = now + 1.0

            wait_seconds = max(0.0, min(deadline, next_query_at) - time.monotonic())
            readable, _, _ = select.select(sockets, [], [], wait_seconds)
            for sock in readable:
                try:
                    raw, (source_ip, _source_port) = sock.recvfrom(1024)
                except (BlockingIOError, OSError):
                    continue
                port = decode_beacon(raw)
                if port is not None:
                    return select_server_url(port, source_ip)
        return None
    except OSError as err:
        logger.warning(f"Nasłuch UDP discovery nieudany: {err}")
        return None
    finally:
        for sock in sockets:
            sock.close()


def _open_interface_sockets() -> list[socket.socket]:
    """Tworzy osobne gniazdo dla każdego adresu IPv4 hosta.

    Samo `bind(("", port))` + broadcast `255.255.255.255` na wielointerfejsowym
    Windowsie wybiera jedną trasę (np. VPN) i omija fizyczny LAN. Przypięcie adresu
    źródłowego zmusza system do wysłania broadcastu właściwym interfejsem, bez
    zgadywania maski podsieci.
    """
    try:
        addresses = sorted(
            {
                item[4][0]
                for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM)
                if item[4][0] != "127.0.0.1"
            }
        )
    except OSError as err:
        logger.warning(f"Nie udało się odczytać lokalnych adresów IPv4: {err}")
        addresses = []

    sockets: list[socket.socket] = []
    for address in addresses or [""]:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind((address, DISCOVERY_UDP_PORT))
        except OSError as err:
            logger.warning(f"Nie udało się otworzyć UDP discovery na [{address or '*'}]: {err}")
            sock.close()
            continue
        sock.setblocking(False)
        sockets.append(sock)
    return sockets
