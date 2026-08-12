from enum import Enum
import time
from pydantic import BaseModel, Field


class ServerEventType(str, Enum):
    """Typy zdarzeń wewnątrz usługi server."""

    SATELLITE_CONNECTED = "satellite.connected"
    SATELLITE_DISCONNECTED = "satellite.disconnected"
    SATELLITE_MESSAGE = "satellite.message"


class SatelliteConnectedPayload(BaseModel):
    """Payload zdarzenia podłączenia satelity."""

    satellite_id: str
    connected_at: float = Field(default_factory=time.time)


class SatelliteDisconnectedPayload(BaseModel):
    """Payload zdarzenia odłączenia satelity."""

    satellite_id: str
    disconnected_at: float = Field(default_factory=time.time)


class SatelliteMessagePayload(BaseModel):
    """Payload zdarzenia wiadomości z satelity."""

    satellite_id: str
    text: str
