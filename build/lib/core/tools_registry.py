import json
import logging
import os
import datetime
import uuid
import requests
from typing import Any

from core.schemas import BASE_TOOLS_SCHEMA


class ToolsRegistry:
    """Rejestr narzędzi dostarczanych dla modelu LLM."""
    
    def __init__(self, ha_client, tier: str = "regis", rooms: dict = None):
        self.ha_client = ha_client
        self.tier = tier
        self.rooms = rooms or {}
        
    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Kieruje wywołanie narzędzia do odpowiedniej logiki."""
        try:
            # Weryfikacja uprawnień na podstawie tieru
            tier_clearance = {"butler": 1, "regis": 2, "prime": 3}
            current_clearance = tier_clearance.get(self.tier, 1)
            
            tool_def = None
            for t in BASE_TOOLS_SCHEMA:
                if t["function"]["name"] == tool_name:
                    tool_def = t
                    break
                    
            if tool_def is None:
                return json.dumps({"error": f"Narzędzie '{tool_name}' nie istnieje."}, ensure_ascii=False)
            
            req_tier = tool_def.get("required_tier", "butler")
            if tier_clearance.get(req_tier, 1) > current_clearance:
                return json.dumps({"error": f"Odmowa dostępu do '{tool_name}' w obecnym trybie."}, ensure_ascii=False)

            dispatch = {
                "get_device_state": lambda: self._get_device_state(arguments.get("entity_id")),
                "execute_action": lambda: self._execute_action(
                    arguments.get("action"), arguments.get("entity_id"), arguments.get("parameters")),
                "get_current_time": lambda: self._get_current_time(),
                "get_weather": lambda: self._get_weather(arguments.get("location")),
            }
            
            handler = dispatch.get(tool_name)
            if handler:
                return handler()
            return json.dumps({"error": f"Nieznane narzędzie: {tool_name}"}, ensure_ascii=False)
            
        except Exception as e:
            logging.error(f"Błąd wykonania narzędzia {tool_name}: {e}")
            return json.dumps({"error": f"Wystąpił błąd podczas wykonania: {str(e)}"}, ensure_ascii=False)

    # ─── Home Assistant ───────────────────────────────────────────────

    def _get_devices(self, domain: str = None, room: str = None) -> str:
        """Zwraca urządzenia z opcjonalnym filtrowaniem po domenie i pokoju.
        
        Ukrywa surowe urządzenia, pozostawiając tylko te "zdefiniowane w abstrakcji":
        - Wirtualne grupy
        - Urządzenia przypisane do pokoi (rooms.json)
        - Urządzenia ze zdefiniowanym aliasem (aliases.json)
        """
        states = self.ha_client.get_all_states()
        room_filter = self.rooms.get(room) if room and self.rooms else None
        devices = []
        
        virtual_groups = getattr(self.ha_client, "virtual_groups", {})
        aliases = getattr(self.ha_client, "aliases", {})
        
        # Zbierz wszystkie encje zdefiniowane w pokojach
        room_entities = set()
        for r_entities in (self.rooms.values() if self.rooms else []):
            room_entities.update(r_entities)
            
        active_virtual_groups = {}
        for vg_id, children in virtual_groups.items():
            vg_domain = vg_id.split(".")[0] if "." in vg_id else ""
            if domain and vg_domain != domain:
                continue
            
            is_in_room = False
            if room_filter is None:
                is_in_room = True
            elif room and room in vg_id: # np. light.moj_pokoj pasuje do room="moj_pokoj"
                is_in_room = True
            else:
                for child in children:
                    if room_filter and child in room_filter:
                        is_in_room = True
                        break
                        
            if is_in_room:
                active_virtual_groups[vg_id] = True
                
        for entity_id, data in states.items():
            if domain and not entity_id.startswith(f"{domain}."):
                continue
            if room_filter is not None and entity_id not in room_filter:
                continue
                
            # Sprawdzenie definicji abstrakcji
            has_alias = entity_id in aliases
            in_room = entity_id in room_entities
            
            # Jeżeli encja składowa należy do jakiejś wirtualnej grupy, nie pokazuj jej osobno
            is_part_of_any_vg = any(entity_id in children for children in virtual_groups.values())
            if is_part_of_any_vg:
                continue
                
            if has_alias or in_room:
                devices.append({"entity_id": entity_id, "name": data.get("friendly_name", "Nieznana Nazwa")})
            
        # Dodaj wirtualne grupy jako jedno syntetyczne urządzenie
        for vg_id in active_virtual_groups:
            domain_part = vg_id.split(".")[0] if "." in vg_id else ""
            name_part = vg_id.split(".")[1].replace("_", " ").title() if "." in vg_id else vg_id
            devices.append({"entity_id": vg_id, "name": f"{name_part} ({domain_part})"})
            
        return json.dumps({"devices": devices}, ensure_ascii=False)

    def get_global_menu(self) -> str:
        """Zwraca sformatowany tekst w Markdown reprezentujący abstrakcyjne urządzenia domowe z uwzględnieniem pokoi."""
        devices_json = json.loads(self._get_devices())
        devices = devices_json.get("devices", [])
        
        entity_to_room = {}
        if getattr(self, "rooms", None):
            for room_name, entity_list in self.rooms.items():
                for ent in entity_list:
                    entity_to_room[ent] = room_name
                    
        grouped_devices = {}
        for dev in devices:
            ent_id = dev["entity_id"]
            name = dev["name"]
            
            room = "Urządzenia bez przypisanego pokoju"
            if ent_id in entity_to_room:
                room = entity_to_room[ent_id]
            else:
                for r_name in (self.rooms.keys() if getattr(self, "rooms", None) else []):
                    if r_name in ent_id:
                        room = r_name
                        break
                        
            if room not in grouped_devices:
                grouped_devices[room] = []
            grouped_devices[room].append(f"- {ent_id} ({name})")
            
        if not devices:
            return "BRAK URZĄDZEŃ W SYSTEMIE."
            
        menu = "DOSTĘPNE URZĄDZENIA (Globalne Menu):\n"
        for room, devs in grouped_devices.items():
            menu += f"\n## Pokój: {room.title()}\n" + "\n".join(devs) + "\n"
            
        return menu.strip()

    def _get_device_state(self, entity_id: str | list[str]) -> str:
        states = self.ha_client.get_all_states()
        
        # Wsparcie dla wirtualnych grup - zagregowany stan
        ha_virtual_groups = getattr(self.ha_client, "virtual_groups", {})
        if isinstance(entity_id, str) and entity_id in ha_virtual_groups:
            children = ha_virtual_groups[entity_id]
            any_on = any(
                child in states and states[child].get("state") == "on" 
                for child in children
            )
            name_part = entity_id.split(".")[-1].replace("_", " ").title()
            return json.dumps({
                "state": "on" if any_on else "off",
                "friendly_name": f"{name_part} (Grupa)"
            }, ensure_ascii=False)
            
        if isinstance(entity_id, list):
            results = {}
            for eid in entity_id:
                if eid in states:
                    results[eid] = states[eid]
                else:
                    results[eid] = {"error": "Urządzenie nie znalezione."}
            return json.dumps(results, ensure_ascii=False)
        else:
            if entity_id in states:
                return json.dumps(states[entity_id], ensure_ascii=False)
            return json.dumps({"error": f"Urządzenie o ID '{entity_id}' nie zostało znalezione."}, ensure_ascii=False)

    def _execute_action(self, action: str, entity_id: str, parameters: dict[str, Any]) -> str:
        if action not in ["turn_on", "turn_off", "toggle"]:
            return json.dumps({"error": f"Nieprawidłowa akcja: '{action}'. Dozwolone: 'turn_on', 'turn_off', 'toggle'. Użyj 'turn_on' do zmiany jasności/koloru."}, ensure_ascii=False)
                
        success = self.ha_client.execute_action(action, entity_id, parameters)
        if success:
            return json.dumps({"result": "success", "message": f"Wykonano {action} na {entity_id}."}, ensure_ascii=False)
        else:
            return json.dumps({"error": f"Akcja {action} nie powiodła się dla {entity_id}."}, ensure_ascii=False)

    # ─── Narzędzia ogólne ─────────────────────────────────────────────

    def _get_current_time(self) -> str:
        now = datetime.datetime.now()
        days = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"]
        day = days[now.weekday()]
        return json.dumps({
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "day_of_week": day
        }, ensure_ascii=False)

    def _get_weather(self, location: str) -> str:
        if not location:
            return json.dumps({"error": "Musisz podać nazwę miasta."}, ensure_ascii=False)
        
        try:
            url = f"https://wttr.in/{location}?format=j1"
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            current = data.get("current_condition", [{}])[0]
            if not current:
                return json.dumps({"error": "Nie znaleziono danych o pogodzie dla podanej lokalizacji."}, ensure_ascii=False)
                
            weather_desc_pl_list = current.get("lang_pl", [])
            weather_desc = weather_desc_pl_list[0].get("value") if weather_desc_pl_list else current.get("weatherDesc", [{}])[0].get("value")
            
            result = {
                "location": location,
                "description": weather_desc,
                "temperature_C": current.get("temp_C"),
                "feels_like_C": current.get("FeelsLikeC"),
                "humidity_percent": current.get("humidity"),
                "wind_speed_kmh": current.get("windspeedKmph")
            }
            return json.dumps(result, ensure_ascii=False)
            
        except requests.exceptions.RequestException as e:
            return json.dumps({"error": f"Nie udało się połączyć z serwisem pogodowym: {str(e)}"}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Błąd parsowania danych o pogodzie: {str(e)}"}, ensure_ascii=False)


