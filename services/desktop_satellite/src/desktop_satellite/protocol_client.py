"""Cienki klient WS `/ws/voice/{sender_id}` — symetryczny do `VoiceConnection` po
stronie serwera (`server/voice/connection.py`), tylko z odwróconą rolą klient/serwer.

Kodowanie i dekodowanie ramek należy do **wspólnego kontraktu**
(`shared/voice_frames.py`), nie do tej klasy: obie usługi robiły to wcześniej ręcznie
i osobno, więc literówka po jednej stronie ujawniała się jako `KeyError` w runtime
po drugiej. Tutaj zostaje samo gniazdo.

Zero logiki automatu stanu — to żyje w `desktop_satellite.session`, dokładnie jak
`VoiceSession` jest oddzielona od `VoiceConnection`.
"""

from __future__ import annotations

from typing import Protocol, Union

import websockets
from shared import (
    HelloFrame,
    SatelliteMessageType,
    ServerFrame,
    decode_server_frame,
    encode_frame,
    get_logger,
    satellite_control_frame,
)
from websockets.asyncio.client import ClientConnection

logger = get_logger("regis.desktop_satellite.protocol")

IncomingFrame = Union[bytes, ServerFrame, None]
"""Co może przyjść z gniazda: surowe audio, zwalidowana ramka kontrolna albo `None`
dla ramki nierozpoznanej (kodek już ją zalogował — automat stanu ją ignoruje)."""


class SatelliteLink(Protocol):
    """Minimalny kontrakt wysyłki używany przez `SatelliteSession` — pozwala
    testować automat stanu bez prawdziwego gniazda (mirror `SatelliteLink` z
    `server/voice/session.py`, tylko w drugą stronę)."""

    async def send_hello(self, capabilities: list[str]) -> None: ...

    async def send_audio(self, chunk: bytes) -> None: ...

    async def send_control(self, message_type: SatelliteMessageType) -> None: ...

    async def recv(self) -> IncomingFrame: ...


class ProtocolClient:
    """Implementacja `SatelliteLink` na prawdziwym gnieździe WS."""

    def __init__(self, server_url: str, sender_id: str) -> None:
        self._url = f"{server_url.rstrip('/')}/{sender_id}"
        # `websockets.connect()` zwraca `ClientConnection` (implementacja asyncio).
        # Dawna adnotacja wskazywała na `websockets.WebSocketClientProtocol` — klasę
        # z przestarzałej gałęzi `legacy`, której `connect()` już nie zwraca; nie
        # wysypywała się w runtime tylko dzięki `from __future__ import annotations`.
        self._ws: ClientConnection | None = None

    async def connect(self) -> None:
        self._ws = await websockets.connect(self._url)

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_hello(self, capabilities: list[str]) -> None:
        await self._send(encode_frame(HelloFrame(capabilities=capabilities)))

    async def send_audio(self, chunk: bytes) -> None:
        await self._require_socket().send(chunk)

    async def send_control(self, message_type: SatelliteMessageType) -> None:
        await self._send(encode_frame(satellite_control_frame(message_type)))

    async def recv(self) -> IncomingFrame:
        raw = await self._require_socket().recv()
        if isinstance(raw, bytes):
            return raw
        return decode_server_frame(raw)

    async def _send(self, payload: str) -> None:
        await self._require_socket().send(payload)

    def _require_socket(self) -> ClientConnection:
        if self._ws is None:
            raise RuntimeError("ProtocolClient.connect() nie zostało wywołane.")
        return self._ws
