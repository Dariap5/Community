import re
with open('app/db/seed.py', 'r') as f:
    code = f.read()
code = code.replace('wait_for_payment=True, config=c_p1', 'config=c_p1')
with open('app/db/seed.py', 'w') as f:
    f.write(code)
