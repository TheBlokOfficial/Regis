"""
Zarządca aktywnych połączeń WebSocket ze Zjednoczonymi Klientami Kontrolera.
"""
from fastapi import WebSocket


class ClientConnectionManager:
    """Zarządza aktywnymi połączeniami WebSocket ze Zjednoczonymi Klientami."""

    def __init__(self):
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, client_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections[client_id] = websocket

    def disconnect(self, client_id: str) -> None:
        if client_id in self.active_connections:
            del self.active_connections[client_id]

    async def send_command(self, client_id: str, command: str, data: dict = None) -> bool:
        """Wysyła komendę do klienta przez WebSocket. Zwraca True jeśli wysłano pomyślnie."""
        from protocol.schemas import WSCommand
        if client_id in self.active_connections:
            try:
                cmd = WSCommand(command=command, data=data or {})
                await self.active_connections[client_id].send_text(cmd.model_dump_json())
                return True
            except Exception:
                self.disconnect(client_id)
        return False


# Globalna instancja — jedyny punkt dostępu do połączeń WebSocket
client_manager = ClientConnectionManager()
