from dataclasses import dataclass
from enum import Enum


class ServerEventType(str, Enum):
    """Typy zdarzeń wewnętrznych serwera Regis."""

    SATELLITE_CONNECTED = "satellite.connected"
    SATELLITE_DISCONNECTED = "satellite.disconnected"
    SATELLITE_MESSAGE = "satellite.message"


@dataclass
class SatelliteConnectedPayload:
    satellite_id: str


@dataclass
class SatelliteDisconnectedPayload:
    satellite_id: str


@dataclass
class SatelliteMessagePayload:
    satellite_id: str
    text: str
