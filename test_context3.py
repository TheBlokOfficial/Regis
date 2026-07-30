import requests, json

sys_prompt = '''Jesteś Regisem, rzeczowym asystentem domowym. Otrzymujesz DOSTĘPNE URZĄDZENIA (Menu) z listą identyfikatorów (`entity_id`) pogrupowanych po pokojach.

# Tools
You may call one or more functions to assist with the user query. You are provided with function signatures within <tools></tools> XML tags:
<tools>
[
  {
    "type": "function",
    "function": {
      "name": "execute_action",
      "description": "Wykonuje akcję na urządzeniu. Bierz entity_id wyłącznie ze swojego Globalnego Menu.",
      "parameters": {
        "type": "object",
        "properties": {
          "action": {"type": "string"},
          "entity_id": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["action", "entity_id"]
      }
    }
  }
]
</tools>
For each function call, return a json object with function name and arguments within <action></action> XML tags:
<action>
{"name": "function-name", "arguments": {}}
</action>'''

messages = [
    {'role': 'system', 'content': sys_prompt}, 
    {'role': 'user', 'content': 'Global Menu:\n- salon:\n  - light.salon\n- biuro:\n  - light.biurko\n\nWyłącz światła'},
    {'role': 'assistant', 'content': '<action>{"name": "execute_action", "arguments": {"action": "turn_off", "entity_id": ["light.salon", "light.biurko"]}}</action>'},
    {'role': 'tool', 'content': 'Success'},
    {'role': 'assistant', 'content': 'Światła zostały wyłączone.'},
    {'role': 'user', 'content': 'A teraz je włącz. (ale tylko te nad biurkiem)'}
]

payload = {
    'model': 'qwen3.5:9b',
    'messages': messages,
    'stream': False
}
try:
    res = requests.post('http://127.0.0.1:11434/api/chat', json=payload).json()
    print('CONTENT:', repr(res.get('message', {}).get('content', '')))
except Exception as e:
    print('Error:', e)
