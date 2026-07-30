import subprocess
import json
import requests

# 1. Pobierz settings z RPi
res = subprocess.run(["ssh", "theblok@192.168.0.119", "cat regis/data/settings.rpi5-controller.json"], capture_output=True, text=True)
settings = json.loads(res.stdout)

# 2. Strzał do HA z Windowsa
token = settings["ha_token"]
url = settings["ha_url"].rstrip("/") + "/api/states"
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

resp = requests.get(url, headers=headers)
states = resp.json()

# Wybierz te włączone
on_lights = []
off_lights = []
for entity in states:
    eid = entity["entity_id"]
    if eid.startswith("light.yeelight"):
        if entity["state"] == "on":
            on_lights.append(eid)
        elif entity["state"] == "off":
            off_lights.append(eid)

print("ON LIGHTS:")
for l in on_lights:
    print(l)
print("\nOFF LIGHTS:")
for l in off_lights:
    print(l)
