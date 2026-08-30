"""Kontrakt UDP discovery — satelita pyta broadcastem, serwer odpowiada unicastem
i dodatkowo rozgłasza cykliczny beacon dla starszych klientów. Dzięki temu nie
trzeba ręcznie wpisywać adresu IP w konfiguracji żadnej satelity.

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
DISCOVERY_QUERY_TYPE = "discover"


def encode_beacon(server_port: int) -> bytes:
    """Koduje payload rozgłoszenia — pole `service` pozwala satelicie odsiać
    przypadkowy ruch UDP innych aplikacji trafiający na ten sam port."""
    return json.dumps({"service": DISCOVERY_MAGIC, "port": server_port}).encode("utf-8")


def encode_discovery_query() -> bytes:
    """Koduje aktywne zapytanie satelity, na które serwer odpowiada unicastem."""
    return json.dumps({"service": DISCOVERY_MAGIC, "type": DISCOVERY_QUERY_TYPE}).encode("utf-8")


def is_discovery_query(raw: bytes) -> bool:
    """Czy payload jest poprawnym aktywnym zapytaniem discovery."""
    payload = _decode_json_object(raw)
    return payload is not None and payload.get("service") == DISCOVERY_MAGIC and payload.get("type") == DISCOVERY_QUERY_TYPE


def decode_beacon(raw: bytes) -> int | None:
    """Dekoduje port serwera z payloadu rozgłoszenia, `None` gdy dane nie są
    poprawnym JSON-em albo nie pochodzą z tego protokołu (obcy `service`)."""
    payload = _decode_json_object(raw)
    if payload is None or payload.get("service") != DISCOVERY_MAGIC:
        return None
    port = payload.get("port")
    return port if isinstance(port, int) else None


def _decode_json_object(raw: bytes) -> dict[str, object] | None:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None
