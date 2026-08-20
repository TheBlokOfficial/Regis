"""Cienki klient WS `/ws/voice/{sender_id}` — koduje/dekoduje ramki zgodnie z
`shared.voice_protocol`, symetrycznie do `VoiceConnection` po stronie serwera
(`server/voice/gateway.py`), tylko z odwróconą rolą klient/serwer.

Zero logiki automatu stanu tutaj — to żyje w `desktop_satellite.session`,
dokładnie jak `VoiceSession` jest oddzielona od `VoiceConnection`.
"""

from __future__ import annotations

import json
from typing import Protocol, Union

import websockets

from shared import SatelliteMessageType, ServerMessageType

ServerFrame = Union[bytes, dict]


class SatelliteLink(Protocol):
    """Minimalny kontrakt wysyłki używany przez `SatelliteSession` — pozwala
    testować automat stanu bez prawdziwego gniazda (mirror `SatelliteLink` z
    `server/voice/session.py`, tylko w drugą stronę)."""

    async def send_hello(self, capabilities: list[str]) -> None: ...

    async def send_audio(self, chunk: bytes) -> None: ...

    async def send_control(self, message_type: SatelliteMessageType) -> None: ...

    async def recv(self) -> ServerFrame: ...


class ProtocolClient:
    """Implementacja `SatelliteLink` na prawdziwym gnieździe WS."""

    def __init__(self, server_url: str, sender_id: str) -> None:
        self._url = f"{server_url.rstrip('/')}/{sender_id}"
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._url)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_hello(self, capabilities: list[str]) -> None:
        await self._send_json({"type": SatelliteMessageType.HELLO.value, "capabilities": capabilities})

    async def send_audio(self, chunk: bytes) -> None:
        assert self._ws is not None, "ProtocolClient.connect() nie zostało wywołane."
        await self._ws.send(chunk)

    async def send_control(self, message_type: SatelliteMessageType) -> None:
        await self._send_json({"type": message_type.value})

    async def recv(self) -> ServerFrame:
        assert self._ws is not None, "ProtocolClient.connect() nie zostało wywołane."
        raw = await self._ws.recv()
        if isinstance(raw, bytes):
            return raw
        return json.loads(raw)

    async def _send_json(self, payload: dict) -> None:
        assert self._ws is not None, "ProtocolClient.connect() nie zostało wywołane."
        await self._ws.send(json.dumps(payload))


def parse_server_message_type(frame: dict) -> ServerMessageType | None:
    """Tłumaczy pole `type` odebranej ramki JSON na `ServerMessageType`, `None` gdy nieznane."""
    try:
        return ServerMessageType(frame.get("type"))
    except ValueError:
        return None
