"""Kodek ramek protokołu głosowego — typowana postać kontraktu z `voice_protocol.py`.

`voice_protocol.py` deklaruje **nazwy** ramek, ale nie potrafi ich zakodować ani
zdekodować. W efekcie obie niezależne usługi robiły to ręcznie i osobno: `json.dumps`
po jednej stronie, `json.loads` + `frame.get("type")` po drugiej, a payload czytany
z surowego dicta (`frame["silence_duration_ms"]` w `desktop_satellite/session.py`).
Był to **jedyny** kontrakt między usługami nietypowany Pydantikiem — REST ma
`shared/contracts.py` i komplet zwalidowanych DTO. Literówka po jednej stronie
ujawniała się dopiero jako `KeyError` w runtime u klienta.

**Format na drucie nie zmienia się**: te same klucze JSON, ta sama semantyka, więc
stara satelita i nowy serwer (oraz odwrotnie) pozostają zgodne.

Podział na dwie rodziny odpowiada kierunkowi ruchu i jest asymetryczny celowo:
serwer dekoduje wyłącznie ramki satelity, satelita wyłącznie ramki serwera. Nieznany
typ daje `None`, nie wyjątek — obie strony logują i idą dalej, dokładnie jak przed
wprowadzeniem kodeka.
"""

from __future__ import annotations

import json
from typing import Annotated, Literal, Type, Union

from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from shared.logging import get_logger
from shared.voice_protocol import SatelliteMessageType, ServerMessageType

logger = get_logger("regis.shared.voice_frames")


# ------------------------------------------------------------------------------
# Satelita -> serwer
# ------------------------------------------------------------------------------


class HelloFrame(BaseModel):
    """Pierwsza ramka po otwarciu połączenia."""

    type: Literal[SatelliteMessageType.HELLO] = SatelliteMessageType.HELLO
    capabilities: list[str] = Field(
        default_factory=list,
        description="Zadeklarowane możliwości klienta (np. ['mic', 'speaker']). Lista, nie enum — "
        "przyszły connector bez audio zadeklaruje mniej.",
    )


class UtteranceEndFrame(BaseModel):
    """Lokalny VAD satelity uznał wypowiedź za zakończoną."""

    type: Literal[SatelliteMessageType.UTTERANCE_END] = SatelliteMessageType.UTTERANCE_END


class PlaybackDoneFrame(BaseModel):
    """Satelita skończyła fizyczne odtwarzanie audio odpowiedzi."""

    type: Literal[SatelliteMessageType.PLAYBACK_DONE] = SatelliteMessageType.PLAYBACK_DONE


SatelliteFrame = Annotated[
    Union[HelloFrame, UtteranceEndFrame, PlaybackDoneFrame],
    Field(discriminator="type"),
]


# ------------------------------------------------------------------------------
# Serwer -> satelita
# ------------------------------------------------------------------------------


class WakeDetectedFrame(BaseModel):
    type: Literal[ServerMessageType.WAKE_DETECTED] = ServerMessageType.WAKE_DETECTED


class PlayStopToneFrame(BaseModel):
    type: Literal[ServerMessageType.PLAY_STOP_TONE] = ServerMessageType.PLAY_STOP_TONE


class TtsStartFrame(BaseModel):
    type: Literal[ServerMessageType.TTS_START] = ServerMessageType.TTS_START


class TtsEndFrame(BaseModel):
    type: Literal[ServerMessageType.TTS_END] = ServerMessageType.TTS_END


class TurnEndFrame(BaseModel):
    """Tura skończona, ale nic nie zostanie odtworzone — satelita wraca do nasłuchu."""

    type: Literal[ServerMessageType.TURN_END] = ServerMessageType.TURN_END


class ErrorFrame(BaseModel):
    type: Literal[ServerMessageType.ERROR] = ServerMessageType.ERROR
    detail: str = Field(default="", description="Sanityzowany opis błędu dla klienta")


class ClientConfigFrame(BaseModel):
    """Parametry VAD satelity — algorytm zostaje lokalny, progi są centralne."""

    type: Literal[ServerMessageType.CLIENT_CONFIG] = ServerMessageType.CLIENT_CONFIG
    silence_duration_ms: float
    amplitude_threshold: int


ServerFrame = Annotated[
    Union[
        WakeDetectedFrame,
        PlayStopToneFrame,
        TtsStartFrame,
        TtsEndFrame,
        TurnEndFrame,
        ErrorFrame,
        ClientConfigFrame,
    ],
    Field(discriminator="type"),
]

# Ramki bez payloadu, budowane po samym typie — pozwala trzymać w automatach stanu
# `send_control(ServerMessageType.X)` zamiast importu siedmiu klas.
_SERVER_CONTROL_FRAMES: dict[ServerMessageType, Type[BaseModel]] = {
    ServerMessageType.WAKE_DETECTED: WakeDetectedFrame,
    ServerMessageType.PLAY_STOP_TONE: PlayStopToneFrame,
    ServerMessageType.TTS_START: TtsStartFrame,
    ServerMessageType.TTS_END: TtsEndFrame,
    ServerMessageType.TURN_END: TurnEndFrame,
}

_SATELLITE_CONTROL_FRAMES: dict[SatelliteMessageType, Type[BaseModel]] = {
    SatelliteMessageType.UTTERANCE_END: UtteranceEndFrame,
    SatelliteMessageType.PLAYBACK_DONE: PlaybackDoneFrame,
}


# ------------------------------------------------------------------------------
# Kodowanie / dekodowanie
# ------------------------------------------------------------------------------


_SERVER_ADAPTER: TypeAdapter[ServerFrame] = TypeAdapter(ServerFrame)
_SATELLITE_ADAPTER: TypeAdapter[SatelliteFrame] = TypeAdapter(SatelliteFrame)


def encode_frame(frame: BaseModel) -> str:
    """Ramka -> tekst JSON gotowy do wysłania przez WebSocket."""
    return frame.model_dump_json()


def server_control_frame(message_type: ServerMessageType) -> BaseModel:
    """Bezpayloadowa ramka serwera po samym typie.

    :raises KeyError: dla typów, które payload NIOSĄ (`ERROR`, `CLIENT_CONFIG`) —
        te trzeba zbudować jawnie, bo pominięcie ich pól byłoby cichym błędem.
    """
    return _SERVER_CONTROL_FRAMES[message_type]()


def satellite_control_frame(message_type: SatelliteMessageType) -> BaseModel:
    """Bezpayloadowa ramka satelity po samym typie (`HELLO` niesie `capabilities`).

    :raises KeyError: dla `HELLO`.
    """
    return _SATELLITE_CONTROL_FRAMES[message_type]()


def decode_server_frame(raw: str) -> ServerFrame | None:
    """Tekst JSON -> zwalidowana ramka serwera; `None` przy nieznanym typie lub złym kształcie.

    Wywołujący (satelita) loguje i wraca do nasłuchu — pojedyncza niezrozumiała ramka
    nie może zrywać połączenia."""
    payload = _load_json(raw, "serwera")
    if payload is None:
        return None
    try:
        return _SERVER_ADAPTER.validate_python(payload)
    except ValidationError as err:
        logger.warning(f"Nierozpoznana ramka od serwera: {payload!r} ({err.error_count()} niezgodności).")
        return None


def decode_satellite_frame(raw: str) -> SatelliteFrame | None:
    """Tekst JSON -> zwalidowana ramka satelity; `None` przy nieznanym typie lub złym kształcie."""
    payload = _load_json(raw, "satelity")
    if payload is None:
        return None
    try:
        return _SATELLITE_ADAPTER.validate_python(payload)
    except ValidationError as err:
        logger.warning(f"Nierozpoznana ramka od satelity: {payload!r} ({err.error_count()} niezgodności).")
        return None


def _load_json(raw: str, origin: str) -> object | None:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(f"Nieprawidłowa ramka JSON od {origin}: {raw!r}")
        return None
