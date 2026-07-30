import json
import logging
import requests
from requests.exceptions import RequestException
from typing import Any

from core.exceptions import HomeAssistantConnectionError

class HomeAssistantClient:
    """Klient zarządzający komunikacją z fizycznym serwerem Home Assistant REST API."""

    def __init__(self, url: str, token: str, aliases: dict[str, str] = None, virtual_groups: dict[str, list[str]] = None):
        """Inicjalizuje klienta HA.
        
        Args:
            url (str): Adres URL serwera Home Assistanta.
            token (str): Długoterminowy token dostępu z HA.
            aliases (dict[str, str], optional): Słownik mapujący skomplikowane nazwy encji na przyjazne.
            virtual_groups (dict[str, list[str]], optional): Mapowanie wirtualnych grup na listy ID.
        """
        self.url = url.rstrip("/")
        self.token = token
        self.aliases = aliases or {}
        self.virtual_groups = virtual_groups or {}
        
        self.session = requests.Session()
        self.session.headers.update(self._get_headers())
        
        logging.info(f"Zainicjalizowano HomeAssistantClient dla URL: {self.url}")

    def _get_headers(self) -> dict[str, str]:
        """Pobiera nagłówki wymagane do autoryzacji żądań HTTP."""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Pobiera z Home Assistanta listę wszystkich encji i ich stanów.
        
        Returns:
            dict[str, dict[str, Any]]: Słownik z aktualnymi stanami odfiltrowanych urządzeń.
        Raises:
            HomeAssistantConnectionError: W przypadku błędu połączenia z HA.
        """
        url = f"{self.url}/api/states"
        
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            allowed_domains = ["light", "switch", "climate", "media_player"]
            filtered_state = {}
            
            for entity in data:
                entity_id = entity["entity_id"]
                domain = entity_id.split(".")[0]
                
                if domain not in allowed_domains:
                    continue
                
                attrs = entity.get("attributes", {})
                original_name = attrs.get("friendly_name")
                if not original_name:
                    # Kiedy encja nie ma nazwy, wyciągnij ładną z entity_id
                    original_name = entity_id.split(".")[-1].replace("_", " ").title()
                
                friendly_name = self.aliases.get(entity_id, original_name)
                
                filtered_state[entity_id] = {
                    "state": entity["state"],
                    "friendly_name": friendly_name
                }
                    
            return filtered_state
        except RequestException as e:
            logging.error(f"[BŁĄD HA] Nie udało się pobrać stanu: {e}")
            raise HomeAssistantConnectionError(f"Nie można pobrać stanów HA: {e}")

    def execute_action(self, action: str, entity_id: str | list[str], parameters: dict[str, Any] | None = None) -> bool:
        """Wysyła polecenie zmiany stanu do fizycznego Home Assistanta.
        
        Args:
            action (str): Typ akcji (np. 'turn_on', 'turn_off').
            entity_id (str | list[str]): Identyfikator/y encji w HA (np. 'light.salon').
            parameters (dict, optional): Dodatkowe parametry przekazywane do usługi (np. {'brightness_pct': 50}).
            
        Returns:
            bool: True jeśli akcja została przyjęta do realizacji.
        Raises:
            HomeAssistantConnectionError: Przy utracie połączenia z serwerem.
        """
        if parameters is None:
            parameters = {}
            
        if isinstance(entity_id, str) and entity_id in self.virtual_groups:
            entity_id = self.virtual_groups[entity_id]
            
        if not isinstance(entity_id, (str, list)):
            logging.warning("[HA CLIENT] Oczekiwano stringa lub listy jako entity_id.")
            return False
            
        # HA obsługuje listę entity_id domyślnie, nie trzeba robić pętli!
        domain = entity_id[0].split(".")[0] if isinstance(entity_id, list) else entity_id.split(".")[0]
        
        if action == "turn_on":
            service = "turn_on"
        elif action == "turn_off":
            service = "turn_off"
        elif action == "toggle":
            service = "toggle"
        else:
            logging.warning(f"[HA CLIENT] Nie obsługiwana akcja: {action}")
            return False
            
        url = f"{self.url}/api/services/{domain}/{service}"
        
        payload_dict = {"entity_id": entity_id}
        if parameters:
            payload_dict.update(parameters)
            
        try:
            response = self.session.post(url, json=payload_dict, timeout=10)
            response.raise_for_status()
            logging.debug(f"[HA CLIENT] Pomyślnie wysłano akcję {service} dla {entity_id}.")
            return True
        except RequestException as e:
            logging.error(f"[BŁĄD HA] Wykonanie akcji odrzucone dla payloadu {payload_dict}: {e}")
            raise HomeAssistantConnectionError(f"Home Assistant odrzucił akcję dla {entity_id}: {e}")
