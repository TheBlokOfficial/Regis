import sys
path='/home/theblok/regis/.venv/lib/python3.13/site-packages/core/agents/nlu_agent.py'
c=open(path).read()
c=c.replace('        try:\n            response = requests.post', '        logging.warning(f"PAYLOAD: {payload}")\n        try:\n            response = requests.post')
open(path, 'w').write(c)
