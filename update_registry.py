import re

with open("src/core/tools_registry.py", "r", encoding="utf-8") as f:
    code = f.read()

# Replace room_entities gathering
old_room_entities = """        # Zbierz wszystkie encje zdefiniowane w pokojach
        room_entities = set()
        for r_entities in (self.rooms.values() if self.rooms else []):
            room_entities.update(r_entities)"""
new_room_entities = """        # Zbierz wszystkie encje zdefiniowane w pokojach
        room_entities = set()
        for r_data in (self.rooms.values() if self.rooms else []):
            if isinstance(r_data, dict):
                room_entities.update(r_data.get("devices", []))
            else:
                room_entities.update(r_data)"""
code = code.replace(old_room_entities, new_room_entities)

# Replace virtual groups formatting in _get_devices
old_vg_formatting = """        # Dodaj wirtualne grupy jako jedno syntetyczne urządzenie
        for vg_id in active_virtual_groups:
            domain_part = vg_id.split(".")[0] if "." in vg_id else ""
            name_part = vg_id.split(".")[1].replace("_", " ").title() if "." in vg_id else vg_id
            devices.append({"entity_id": vg_id, "name": f"{name_part} ({domain_part})"})"""
new_vg_formatting = """        # Dodaj wirtualne grupy jako jedno syntetyczne urządzenie
        for vg_id in active_virtual_groups:
            domain_part = vg_id.split(".")[0] if "." in vg_id else ""
            name_part = vg_id.split(".")[1].replace("_", " ").title() if "." in vg_id else vg_id
            
            vg_children = virtual_groups.get(vg_id, [])
            nested_vgs = [c for c in vg_children if c in virtual_groups]
            
            devices.append({
                "entity_id": vg_id, 
                "name": f"{name_part} (Grupa)",
                "nested": nested_vgs
            })"""
code = code.replace(old_vg_formatting, new_vg_formatting)

# Replace get_global_menu
old_global_menu = """    def get_global_menu(self) -> str:
        \"\"\"Zwraca sformatowany tekst w Markdown reprezentujący abstrakcyjne urządzenia domowe z uwzględnieniem pokoi.\"\"\"
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
            
        menu = "DOSTĘPNE URZĄDZENIA (Globalne Menu):\\n"
        for room, devs in grouped_devices.items():
            menu += f"\\n## Pokój: {room.title()}\\n" + "\\n".join(devs) + "\\n"
            
        return menu.strip()"""
new_global_menu = """    def get_global_menu(self) -> str:
        \"\"\"Zwraca sformatowany tekst w Markdown reprezentujący abstrakcyjne urządzenia domowe z uwzględnieniem pokoi.\"\"\"
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
            
        menu = "DOSTĘPNE URZĄDZENIA (Globalne Menu):\\n"
        for room, devs in grouped_devices.items():
            menu += f"\\n## Pokój: {room}\\n"
            orig_room = next((k for k, v in self.rooms.items() if (v.get("name") if isinstance(v, dict) else k.title()) == room), None)
            if orig_room and orig_room in room_metadata and room_metadata[orig_room]:
                meta_str = ", ".join(room_metadata[orig_room])
                menu += f"*Metadane: {meta_str}*\\n"
            menu += "\\n".join(devs) + "\\n"
            
        return menu.strip()"""
code = code.replace(old_global_menu, new_global_menu)

# Replace _get_device_state
old_device_state = """        # Wsparcie dla wirtualnych grup - zagregowany stan
        ha_virtual_groups = getattr(self.ha_client, "virtual_groups", {})
        if isinstance(entity_id, str) and entity_id in ha_virtual_groups:
            children = ha_virtual_groups[entity_id]
            any_on = any(
                child in states and states[child].get("state") == "on" 
                for child in children
            )"""
new_device_state = """        # Wsparcie dla wirtualnych grup - zagregowany stan
        ha_virtual_groups = getattr(self.ha_client, "virtual_groups", {})
        if isinstance(entity_id, str) and entity_id in ha_virtual_groups:
            children = self.ha_client._flatten_entities(entity_id) if hasattr(self.ha_client, "_flatten_entities") else ha_virtual_groups[entity_id]
            any_on = any(
                child in states and states[child].get("state") == "on" 
                for child in children
            )"""
code = code.replace(old_device_state, new_device_state)

with open("src/core/tools_registry.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Updated tools_registry.py successfully.")
