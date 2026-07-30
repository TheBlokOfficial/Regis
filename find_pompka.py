import subprocess
import json
import requests

# 1. Pobierz settings z RPi
res = subprocess.run(["ssh", "theblok@192.168.0.119", "cat regis/data/settings.rpi5-controller.json"], capture_output=True, text=True)
settings = json.loads(res.stdout)

token = settings["ha_token"]
url = settings["ha_url"].rstrip("/") + "/api/states"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

resp = requests.get(url, headers=headers)
states = resp.json()

print("Szukam urządzeń z frazami: 'pompka', 'shelly', 'pump'...")
for entity in states:
    eid = entity["entity_id"].lower()
    friendly_name = entity.get("attributes", {}).get("friendly_name", "").lower()
    
    if "pomp" in eid or "pomp" in friendly_name or "shelly" in eid or "shelly" in friendly_name:
        print(f"ZNAZLEZIONO: {entity['entity_id']} | Nazwa: {entity.get('attributes', {}).get('friendly_name')} | Stan: {entity['state']}")
