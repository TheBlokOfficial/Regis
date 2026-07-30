import sys, os
sys.path.append(os.path.join(os.getcwd(), 'src'))
from core.agents.react_agent import ReActAgent
from core.stream_parser import StreamingTokenParser
from core import config
from core.schemas import render_tools_for_prompt

class DummyRegistry:
    def execute_tool(self, name, args): return 'Success'

agent = ReActAgent('qwen3.5:9b', 0.1)
parser = StreamingTokenParser(lambda x: print('THOUGHT:', x), lambda x: print('TEXT:', x))

with open(os.path.join(config.CONFIG_DIR, 'prompts', 'tier_regis.md'), 'r', encoding='utf-8') as f:
    sys_prompt = f.read()

sys_prompt += '\n\n' + render_tools_for_prompt('regis')

messages = [
    {'role': 'system', 'content': sys_prompt}, 
    {'role': 'user', 'content': 'Global Menu:\n- salon:\n  - light.salon\n- biuro:\n  - light.biurko\n\nWyłącz światła'},
    {'role': 'assistant', 'content': '<action>{"name": "execute_action", "arguments": {"action": "turn_off", "entity_id": ["light.salon", "light.biurko"]}}</action>'},
    {'role': 'tool', 'content': 'Success'},
    {'role': 'assistant', 'content': 'Światła zostały wyłączone.'},
    {'role': 'user', 'content': 'A teraz je włącz. (ale tylko te nad biurkiem)'}
]

res = agent.generate_response(messages, DummyRegistry(), parser, lambda x: print('TOOL:', x), lambda x: None, lambda x: None)
print('FINAL RETURN:', repr(res))
