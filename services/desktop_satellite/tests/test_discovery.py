"""Testy czystych funkcji discovery — bez gniazd UDP.

`encode_beacon`/`decode_beacon` żyją w `shared.discovery` (kontrakt
współdzielony przez `server` i `desktop_satellite`), `select_server_url`
w `desktop_satellite.discovery` (budowa adresu WS po stronie klienta).
"""

from desktop_satellite.discovery import select_server_url
from shared import decode_beacon, encode_beacon


def test_encode_decode_beacon_round_trip() -> None:
    raw = encode_beacon(8000)
    assert decode_beacon(raw) == 8000


def test_decode_beacon_rejects_non_json() -> None:
    assert decode_beacon(b"not json") is None


def test_decode_beacon_rejects_foreign_service() -> None:
    raw = b'{"service": "some-other-app", "port": 8000}'
    assert decode_beacon(raw) is None


def test_decode_beacon_rejects_non_int_port() -> None:
    raw = b'{"service": "regis-satellite-discovery-v1", "port": "8000"}'
    assert decode_beacon(raw) is None


def test_select_server_url_builds_ws_url() -> None:
    assert select_server_url(8000, "192.168.1.10") == "ws://192.168.1.10:8000/ws/voice"
