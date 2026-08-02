import json
import logging
import time
import requests
from requests.exceptions import RequestException
from typing import Any

from core.exceptions import HomeAssistantConnectionError

logger = logging.getLogger(__name__)

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

    def check_connection(self) -> bool:
        """Sprawdza czy połączenie z serwerem Home Assistant działa prawidłowo."""
        url = f"{self.url}/api/"
        try:
            resp = self.session.get(url, timeout=5)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.debug(f"[HA CLIENT] check_connection nie powiodło się: {e}")
            raise HomeAssistantConnectionError(f"Nie można połączyć z HA: {e}")

    def get_all_states(self) -> dict[str, dict[str, Any]]:
        """Pobiera z Home Assistanta listę wszystkich encji i ich stanów.
        
        Returns:
            dict[str, dict[str, Any]]: Słownik z aktualnymi stanami odfiltrowanych urządzeń.
        Raises:
            HomeAssistantConnectionError: W przypadku błędu połączenia z HA.
        """
        url = f"{self.url}/api/states"
        logger.debug(f"HA GET {url}")
        _t = time.perf_counter()
        
        try:
            response = self.session.get(url, timeout=10)
            elapsed_ms = int((time.perf_counter() - _t) * 1000)
            response.raise_for_status()
            data = response.json()
            logger.debug(f"HA response: {response.status_code} OK | {elapsed_ms}ms | encji surowych: {len(data)}")
            
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
                
                state_dict = {
                    "state": entity["state"],
                    "friendly_name": friendly_name
                }
                
                # Tylko z góry określone, lekkie klucze by nie marnować tokenów
                important_keys = ["brightness", "color_temp", "rgb_color", "temperature", "current_temperature", "volume_level", "media_title"]
                extracted_attrs = {}
                for k in important_keys:
                    if k in attrs and attrs[k] is not None:
                        val = attrs[k]
                        # Zamiana z 0-255 na procenty od razu w backendzie
                        if k == "brightness":
                            val = round((val / 255.0) * 100)
                            extracted_attrs["brightness_pct"] = val
                        else:
                            extracted_attrs[k] = val
                
                # Wymuszamy dodanie słownika atrybutów (nawet jeśli pusty), 
                # aby Węzeł na Windowsie łatwiej wstrzykiwał jednolity format
                state_dict["attributes"] = extracted_attrs
                    
                filtered_state[entity_id] = state_dict
                    
            logger.debug(f"HA get_all_states: po filtrowaniu {len(filtered_state)} encji (domeny: {allowed_domains})")
            return filtered_state
        except RequestException as e:
            logging.error(f"[BŁĄD HA] Nie udało się pobrać stanu: {e}")
            raise HomeAssistantConnectionError(f"Nie można pobrać stanów HA: {e}")
    def get_phone_battery(self) -> dict[str, str]:
        """Pobiera i tłumaczy stan baterii telefonu dla LLM."""
        url_lvl = f"{self.url}/api/states/sensor.pixel_9a_battery_level"
        url_state = f"{self.url}/api/states/sensor.pixel_9a_battery_state"
        
        try:
            _t = time.perf_counter()
            resp_lvl = self.session.get(url_lvl, timeout=5)
            resp_state = self.session.get(url_state, timeout=5)
            elapsed_ms = int((time.perf_counter() - _t) * 1000)

            level = resp_lvl.json().get("state", "unknown") if resp_lvl.status_code == 200 else "unknown"
            raw_status = resp_state.json().get("state", "unknown") if resp_state.status_code == 200 else "unknown"
            logger.debug(
                f"HA get_phone_battery | {elapsed_ms}ms "
                f"| level_status={resp_lvl.status_code} raw_level={level!r} "
                f"| state_status={resp_state.status_code} raw_status={raw_status!r}"
            )
            
            # Mapowanie stanów na czystsze i łatwiejsze do zrozumienia dla LLM
            state_mapping = {
                "discharging": "not_charging",
                "charging": "charging",
                "full": "full",
                "not_charging": "not_charging"
            }
            status = state_mapping.get(raw_status, raw_status)
            logger.debug(f"HA get_phone_battery state_mapping: {raw_status!r} -> {status!r}")
            
            return {
                "battery_level": f"{level}%" if level != "unknown" else level,
                "battery_state": status
            }
        except RequestException as e:
            logging.error(f"[BŁĄD HA] Nie udało się pobrać baterii: {e}")
            return {"battery_level": "unknown", "battery_state": "error"}

    def _flatten_entities(self, entity_ids: str | list[str]) -> list[str]:
        """Rekurencyjnie spłaszcza grupy wirtualne do listy fizycznych encji."""
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
            
        flat_list = []
        for eid in entity_ids:
            if eid in self.virtual_groups:
                for child in self._flatten_entities(self.virtual_groups[eid]):
                    if child not in flat_list:
                        flat_list.append(child)
            else:
                if eid not in flat_list:
                    flat_list.append(eid)
        return flat_list

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
            
        entity_id = self._flatten_entities(entity_id)
        if not entity_id:
            logging.warning("[HA CLIENT] Pusta lista encji po rozpakowaniu.")
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

        logger.debug(f"HA POST {url} | payload: {payload_dict}")
        _t = time.perf_counter()
        try:
            response = self.session.post(url, json=payload_dict, timeout=10)
            elapsed_ms = int((time.perf_counter() - _t) * 1000)
            response.raise_for_status()
            logger.debug(f"HA response: {response.status_code} OK | {elapsed_ms}ms | akcja: {service} na {entity_id}")
            logging.debug(f"[HA CLIENT] Pomyślnie wysłano akcję {service} dla {entity_id}.")
            return True
        except RequestException as e:
            logging.error(f"[BŁĄD HA] Wykonanie akcji odrzucone dla payloadu {payload_dict}: {e}")
            raise HomeAssistantConnectionError(f"Home Assistant odrzucił akcję dla {entity_id}: {e}")
