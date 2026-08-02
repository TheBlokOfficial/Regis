import json
import logging
import requests
from typing import Any


class RemoteToolsRegistry:
    """Proxy rejestru narzędzi — deleguje wykonanie do Kontrolera przez HTTP.

    Używany przez Węzeł Roboczy, który nie ma bezpośredniego dostępu do
    Home Assistant. Kontroler jest jedynym źródłem prawdy (MANIFEST.md §3.1).

    Implementuje ten sam interfejs co ToolsRegistry (metoda execute_tool),
    dzięki czemu LLMEngine nie wymaga żadnych zmian — podmiana jest transparentna.
    """

    def __init__(self, controller_url: str, room: str | None = None):
        """
        Args:
            controller_url: Bazowy URL Kontrolera (np. 'http://192.168.0.119:8000').
            room: Kontekst pokoju Satelity — przekazywany w każdym wywołaniu narzędzia.
        """
        self.controller_url = controller_url.rstrip("/")
        self.room = room
        self.session = requests.Session()

    def get_global_menu(self) -> str:
        """Pobiera skompilowane Globalne Menu od Kontrolera."""
        try:
            response = self.session.get(f"{self.controller_url}/v1/tools/menu", timeout=10)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.error(f"Błąd pobierania Globalnego Menu z Kontrolera: {e}")
            return "BRAK URZĄDZEŃ (BŁĄD ZASOBÓW)"

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Deleguje wywołanie narzędzia do Kontrolera przez HTTP POST.

        Args:
            tool_name: Nazwa narzędzia (np. 'execute_ha_action').
            arguments: Argumenty wywołania narzędzia.

        Returns:
            Wynik narzędzia jako string JSON (identyczny format jak ToolsRegistry).
        """
        try:
            response = self.session.post(
                f"{self.controller_url}/v1/tools/execute",
                json={"tool_name": tool_name, "arguments": arguments, "room": self.room},
                timeout=30
            )
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.error(f"Błąd proxy narzędzia '{tool_name}': {e}")
            return json.dumps(
                {"error": f"Nie można wykonać narzędzia przez Kontroler: {e}"},
                ensure_ascii=False
            )
