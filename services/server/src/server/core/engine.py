from shared import Event, EventBus, get_logger
from server.core.events import (
    SatelliteConnectedPayload,
    SatelliteDisconnectedPayload,
    SatelliteMessagePayload,
    ServerEventType,
)

logger = get_logger("regis.agent")


class AgentEngine:
    """Rdzeń Systemu Operacyjnego Agenta AI (Agent OS Kernel).

    Zarządza stanem agenta, pamięcią, narzędziami oraz przetwarzaniem
    strumieni audio i komend z satelitów poprzez magistralę zdarzeń.
    """

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.is_running: bool = False

    async def initialize(self) -> None:
        """Inicjalizacja podsystemów agenta oraz subskrypcji zdarzeń."""
        logger.info("Inicjalizacja Agent Engine Kernel...")

        # Subskrybujemy silnie typowane zdarzenia wewnętrzne serwera
        self.event_bus.subscribe(ServerEventType.SATELLITE_CONNECTED, self._on_satellite_connected)
        self.event_bus.subscribe(ServerEventType.SATELLITE_DISCONNECTED, self._on_satellite_disconnected)
        self.event_bus.subscribe(ServerEventType.SATELLITE_MESSAGE, self._on_satellite_message)

        self.is_running = True
        logger.info("Agent Engine jest gotowy i nasłuchuje na magistrali zdarzeń.")

    async def shutdown(self) -> None:
        """Bezpieczne zamknięcie rdzenia agenta."""
        logger.info("Zamykanie Agent Engine...")
        self.is_running = False

    async def _on_satellite_connected(self, event: Event[SatelliteConnectedPayload]) -> None:
        payload = event.payload
        logger.info(f"🟢 Detected new satellite online: [{payload.satellite_id}]")

    async def _on_satellite_disconnected(self, event: Event[SatelliteDisconnectedPayload]) -> None:
        payload = event.payload
        logger.info(f"🔴 Satellite went offline: [{payload.satellite_id}]")

    async def _on_satellite_message(self, event: Event[SatelliteMessagePayload]) -> None:
        payload = event.payload
        logger.info(f"💬 Przetwarzanie wiadomości od satelity [{payload.satellite_id}]: {payload.text}")
