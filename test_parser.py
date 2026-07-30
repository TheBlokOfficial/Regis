import json
import re

response_text = """<thought>
Użytkownik chce włączyć światło. Zgodnie z DOSTĘPNymi URZĄDZENIAMI, mogę to zrobić dla pokoju `moj_pokoj`. Nie
potrzebuję sprawdzać stanu światła przed włączaniem, bo jestem pewien, że mogę to zrobić bezpośrednio.
</thought>
<tool_call>
{"name": "execute_action", "arguments": {"action": "turn_on", "entity_id": "light.moj_pokoj"}}"""

all_known_tools = ["execute_action"]

tag_match = re.search(r'<tool_call>\s*(\{.*?\})\s*(?:</tool_call>)?', response_text, re.DOTALL)
if tag_match:
    print("MATCH 1")
    try:
        parsed = json.loads(tag_match.group(1))
        func_name = parsed.get("name", "")
        print("FUNC 1:", func_name)
    except json.JSONDecodeError as e:
        print("JSON Error 1:", e)
        print("TEXT:", tag_match.group(1))
else:
    print("NO MATCH 1")

stack = []
start_idx = -1
in_string = False
escape_next = False
extracted_jsons = []

for i, char in enumerate(response_text):
    if escape_next:
        escape_next = False
        continue
    if char == '\\':
        escape_next = True
        continue
    if char == '"':
        in_string = not in_string
        continue
    if not in_string:
        if char == '{':
            if not stack:
                start_idx = i
            stack.append(char)
        elif char == '}':
            if stack:
                stack.pop()
                if not stack:
                    json_str = response_text[start_idx:i+1]
                    try:
                        parsed = json.loads(json_str)
                        if isinstance(parsed, dict) and parsed.get("name") in all_known_tools:
                            extracted_jsons.append((parsed, start_idx, i+1))
                    except json.JSONDecodeError as e:
                        print("JSON Error 2:", e)

if extracted_jsons:
    print("MATCH 2", extracted_jsons[0][0])
else:
    print("NO MATCH 2")
