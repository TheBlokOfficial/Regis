import urllib.request, json
url = 'http://192.168.0.50:8123/api/states'
req = urllib.request.Request(url, headers={'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiI1ZTk1NmI3MjQ1M2Y0MGM2ODRiYWU4NzA4Yjk4NTMwMCIsImlhdCI6MTc4NTEzMzgzNCwiZXhwIjoyMTAwNDkzODM0fQ.AGP0Pxrl0X0aU3WzzdrcQ6ztn-TLBJoctDcB23ImRTk', 'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req) as response:
        states = json.loads(response.read().decode())
        for state in states:
            if 'pixel_9a' in state['entity_id'].lower() or 'battery' in state['entity_id'].lower():
                print(f"{state['entity_id']}: {state['state']}")
except Exception as e:
    print('Error:', e)
