import json

data = [
    {
        "entity_id": "light.moj_pokoj_zarowka",
        "state": "on",
        "attributes": {
            "brightness": 255,
            "friendly_name": "Moja zarowka",
            "supported_color_modes": ["brightness"]
        }
    },
    {
        "entity_id": "light.druga",
        "state": "off",
        "attributes": {
            "friendly_name": "Wylaczona"
        }
    }
]

allowed_domains = ["light", "switch", "climate", "media_player"]
filtered_state = {}
aliases = {}

for entity in data:
    entity_id = entity["entity_id"]
    domain = entity_id.split(".")[0]
    
    if domain not in allowed_domains:
        continue
    
    attrs = entity.get("attributes", {})
    original_name = attrs.get("friendly_name")
    if not original_name:
        original_name = entity_id.split(".")[-1].replace("_", " ").title()
    
    friendly_name = aliases.get(entity_id, original_name)
    
    state_dict = {
        "state": entity["state"],
        "friendly_name": friendly_name
    }
    
    important_keys = ["brightness", "color_temp", "rgb_color", "temperature", "current_temperature", "volume_level", "media_title"]
    extracted_attrs = {k: attrs[k] for k in important_keys if k in attrs and attrs[k] is not None}
    if extracted_attrs:
        state_dict["attributes"] = extracted_attrs
        
    filtered_state[entity_id] = state_dict

print(json.dumps(filtered_state, indent=2))

virtual_groups = {"light.moj_pokoj": ["light.moj_pokoj_zarowka", "light.druga"]}
entity_id = "light.moj_pokoj"
children = virtual_groups[entity_id]

any_on = any(child in filtered_state and filtered_state[child].get("state") == "on" for child in children)
name_part = entity_id.split(".")[-1].replace("_", " ").title()

group_response = {
    "state": "on" if any_on else "off",
    "friendly_name": f"{name_part} (Grupa)"
}

for child in children:
    if child in filtered_state and filtered_state[child].get("state") == "on" and "attributes" in filtered_state[child]:
        group_response["attributes"] = filtered_state[child]["attributes"]
        break

print("GROUP RESPONSE:", json.dumps(group_response))
