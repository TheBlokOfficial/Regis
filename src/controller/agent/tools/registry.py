import json
import logging
import os
import datetime
import uuid
import requests
from typing import Any

import controller.core.app_state as app_state
from controller.agent.tools.schemas import BASE_TOOLS_SCHEMA


class ToolsRegistry:
    """Rejestr narzędzi dostarczanych dla modelu LLM."""

    def __init__(self, ha_client=None, rooms: dict = None, integration_registry: dict = None):
        self._direct_ha_client = ha_client
        self._integration_registry = integration_registry
        if rooms is None:
            from controller.config import load, RoomsConfig
            self.rooms = load(RoomsConfig).root
        else:
            self.rooms = rooms

    @property
    def ha_client(self):
        """Zwraca obiekt integracji/klienta HA dla operacji na urządzeniach."""
        if self._direct_ha_client is not None:
            return self._direct_ha_client
        ints = self._integration_registry or app_state.integration_registry
        if "home_assistant" in ints:
            return ints["home_assistant"]
        return app_state.ha_client

    def execute_tool(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Kieruje wywołanie narzędzia do odpowiedniej logiki."""
        try:
            tool_def = next((t for t in BASE_TOOLS_SCHEMA if t["function"]["name"] == tool_name), None)

            if tool_def is None:
                return json.dumps({"error": f"Narzędzie '{tool_name}' nie istnieje."}, ensure_ascii=False)

            dispatch = {
                "get_device_state": lambda: self._get_device_state(arguments.get("entity_id")),
                "execute_action": lambda: self._execute_action(
                    arguments.get("action"), arguments.get("entity_id"), arguments.get("parameters")),
                "get_current_time": lambda: self._get_current_time(),
                "get_weather": lambda: self._get_weather(arguments.get("location")),
                "get_phone_battery": lambda: self._get_phone_battery(),
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
        """Zwraca urządzenia z opcjonalnym filtrowaniem po domenie i pokoju."""
        states = self.ha_client.get_all_states()
        room_filter = self.rooms.get(room) if room and self.rooms else None
        devices = []

        virtual_groups = getattr(self.ha_client, "virtual_groups", {})
        aliases = getattr(self.ha_client, "aliases", {})

        room_entities = set()
        for r_data in (self.rooms.values() if self.rooms else []):
            if isinstance(r_data, dict):
                room_entities.update(r_data.get("devices", []))
            else:
                room_entities.update(r_data)

        active_virtual_groups = {}
        for vg_id, children in virtual_groups.items():
            vg_domain = vg_id.split(".")[0] if "." in vg_id else ""
            if domain and vg_domain != domain:
                continue

            is_in_room = False
            if room_filter is None:
                is_in_room = True
            elif room and room in vg_id:
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

            has_alias = entity_id in aliases
            in_room = entity_id in room_entities

            is_part_of_any_vg = any(entity_id in children for children in virtual_groups.values())
            if is_part_of_any_vg:
                continue

            if has_alias or in_room:
                devices.append({"entity_id": entity_id, "name": data.get("friendly_name", "Nieznana Nazwa")})

        for vg_id in active_virtual_groups:
            name_part = vg_id.split(".")[1].replace("_", " ").title() if "." in vg_id else vg_id
            vg_children = virtual_groups.get(vg_id, [])
            nested_vgs = [c for c in vg_children if c in virtual_groups]
            devices.append({
                "entity_id": vg_id,
                "name": f"{name_part} (Grupa)",
                "nested": nested_vgs
            })

        return json.dumps({"devices": devices}, ensure_ascii=False)

    def get_global_menu(self) -> str:
        """Zwraca sformatowany tekst w Markdown reprezentujący abstrakcyjne urządzenia domowe."""
        devices_json = json.loads(self._get_devices())
        devices = devices_json.get("devices", [])

        entity_to_room = {}
        room_metadata = {}
        if getattr(self, "rooms", None):
            for room_name, r_data in self.rooms.items():
                if isinstance(r_data, dict):
                    room_metadata[room_name] = r_data.get("metadata", [])
                    display_name = r_data.get("name", room_name.title())
                    for ent in r_data.get("devices", []):
                        entity_to_room[ent] = display_name
                else:
                    for ent in r_data:
                        entity_to_room[ent] = room_name.title()

        grouped_devices = {}
        for dev in devices:
            ent_id = dev["entity_id"]
            name = dev["name"]
            nested = dev.get("nested", [])

            room = "Urządzenia bez przypisanego pokoju"
            if ent_id in entity_to_room:
                room = entity_to_room[ent_id]
            else:
                for r_name in (self.rooms.keys() if getattr(self, "rooms", None) else []):
                    if r_name in ent_id:
                        r_data = self.rooms[r_name]
                        room = r_data.get("name", r_name.title()) if isinstance(r_data, dict) else r_name.title()
                        break

            if room not in grouped_devices:
                grouped_devices[room] = []

            entry = f"- {ent_id} ({name})"
            if nested:
                entry += f" [Zawiera: {', '.join(nested)}]"
            grouped_devices[room].append(entry)

        if not devices:
            return "BRAK URZĄDZEŃ W SYSTEMIE."

        menu = "DOSTĘPNE URZĄDZENIA (Globalne Menu):\n"
        for room, devs in grouped_devices.items():
            menu += f"\n## Pokój: {room}\n"
            orig_room = next((k for k, v in self.rooms.items() if (v.get("name") if isinstance(v, dict) else k.title()) == room), None)
            if orig_room and orig_room in room_metadata and room_metadata[orig_room]:
                meta_str = ", ".join(room_metadata[orig_room])
                menu += f"*Metadane: {meta_str}*\n"
            menu += "\n".join(devs) + "\n"

        return menu.strip()

    def _get_device_state(self, entity_id: str | list[str]) -> str:
        states = self.ha_client.get_all_states()
        ha_virtual_groups = getattr(self.ha_client, "virtual_groups", {})

        is_single_string = isinstance(entity_id, str)
        eids = [entity_id] if is_single_string else entity_id

        results = {}
        for eid in eids:
            if eid in ha_virtual_groups:
                children = self.ha_client._flatten_entities(eid) if hasattr(self.ha_client, "_flatten_entities") else ha_virtual_groups[eid]
                any_on = any(child in states and states[child].get("state") == "on" for child in children)
                name_part = eid.split(".")[-1].replace("_", " ").title()
                group_response = {
                    "state": "on" if any_on else "off",
                    "friendly_name": f"{name_part} (Grupa)",
                    "attributes": {}
                }
                for child in children:
                    if child in states and states[child].get("state") == "on" and "attributes" in states[child]:
                        group_response["attributes"].update(states[child]["attributes"])
                results[eid] = group_response
            elif eid in states:
                results[eid] = states[eid]
            else:
                results[eid] = {"error": "Urządzenie nie znalezione."}

        if is_single_string:
            return json.dumps(results[entity_id], ensure_ascii=False)
        else:
            return json.dumps(results, ensure_ascii=False)

    def _get_phone_battery(self) -> str:
        try:
            data = self.ha_client.get_phone_battery()
            return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            logging.error(f"Błąd w delegacji pobierania baterii: {e}")
            return json.dumps({"battery_level": "unknown", "battery_state": "error"}, ensure_ascii=False)

    def _execute_action(self, action: str, entity_id: str, parameters: dict[str, Any]) -> str:
        if action not in ["turn_on", "turn_off", "toggle"]:
            return json.dumps({"error": f"Nieprawidłowa akcja: '{action}'. Dozwolone: 'turn_on', 'turn_off', 'toggle'."}, ensure_ascii=False)

        try:
            success = self.ha_client.execute_action(action, entity_id, parameters)
            if success:
                return json.dumps({"result": "success", "message": f"Wykonano {action} na {entity_id}."}, ensure_ascii=False)
            else:
                return json.dumps({"error": f"Akcja {action} nie powiodła się dla {entity_id}."}, ensure_ascii=False)
        except ValueError as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": f"Wystąpił błąd podczas wywoływania akcji: {e}"}, ensure_ascii=False)

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
                return json.dumps({"error": "Nie znaleziono danych o pogodzie."}, ensure_ascii=False)

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
