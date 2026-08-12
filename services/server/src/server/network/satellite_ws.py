from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from shared import Event, EventBus, get_logger
from server.agent.events import (
    SatelliteConnectedPayload,
    SatelliteDisconnectedPayload,
    SatelliteMessagePayload,
    ServerEventType,
)

logger = get_logger("regis.network.ws")
router = APIRouter()


def register_satellite_websocket(app_router: APIRouter, event_bus: EventBus) -> None:
    """Rejestracja endpointów WebSocket dla satelitów połączonych z magistralą zdarzeń."""

    @app_router.websocket("/ws/satellite/{satellite_id}")
    async def satellite_websocket_endpoint(websocket: WebSocket, satellite_id: str):
        await websocket.accept()
        logger.info(f"Nawiązano połączenie WebSocket z satelitą: [{satellite_id}]")

        # Rozgłaszamy silnie typowane zdarzenie połączenia satelity
        await event_bus.publish(
            Event(
                type=ServerEventType.SATELLITE_CONNECTED,
                payload=SatelliteConnectedPayload(satellite_id=satellite_id),
                sender=f"ws.{satellite_id}",
            )
        )

        try:
            while True:
                data = await websocket.receive_text()
                # Rozgłaszamy odebraną wiadomość z użyciem Pydantic payloadu
                await event_bus.publish(
                    Event(
                        type=ServerEventType.SATELLITE_MESSAGE,
                        payload=SatelliteMessagePayload(satellite_id=satellite_id, text=data),
                        sender=f"ws.{satellite_id}",
                    )
                )
                await websocket.send_text(f"Echo magistrali zdarzeń: ODEBRANO '{data}'")
        except WebSocketDisconnect:
            logger.info(f"Rozłączono połączenie WebSocket z satelitą: [{satellite_id}]")
            await event_bus.publish(
                Event(
                    type=ServerEventType.SATELLITE_DISCONNECTED,
                    payload=SatelliteDisconnectedPayload(satellite_id=satellite_id),
                    sender=f"ws.{satellite_id}",
                )
            )
