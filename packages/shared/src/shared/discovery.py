"""Kontrakt UDP discovery — serwer rozgłasza swoją obecność w sieci lokalnej
(broadcast), satelity nasłuchują, żeby nie trzeba było ręcznie wpisywać adresu
IP w konfiguracji każdej z nich.

Model bez uwierzytelniania, spójny z resztą systemu (`WS /ws/voice/{sender_id}`
też bez auth) — świadome założenie zaufanej sieci lokalnej, patrz
`docs/manifest.md`, sekcja 5.

Moduł żyje w `packages/shared`, nie w `services/server`, z tego samego powodu
co `voice_protocol.py`: to kontrakt między dwiema niezależnymi usługami
(`server` i `desktop_satellite`).
"""

from __future__ import annotations

import json

DISCOVERY_UDP_PORT = 41530
DISCOVERY_MAGIC = "regis-satellite-discovery-v1"


def encode_beacon(server_port: int) -> bytes:
    """Koduje payload rozgłoszenia — pole `service` pozwala satelicie odsiać
    przypadkowy ruch UDP innych aplikacji trafiający na ten sam port."""
    return json.dumps({"service": DISCOVERY_MAGIC, "port": server_port}).encode("utf-8")


def decode_beacon(raw: bytes) -> int | None:
    """Dekoduje port serwera z payloadu rozgłoszenia, `None` gdy dane nie są
    poprawnym JSON-em albo nie pochodzą z tego protokołu (obcy `service`)."""
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("service") != DISCOVERY_MAGIC:
        return None
    port = payload.get("port")
    return port if isinstance(port, int) else None
