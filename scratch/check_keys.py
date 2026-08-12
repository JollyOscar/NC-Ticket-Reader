import re
with open("app.py", "r", encoding="utf-8") as f:
    text = f.read()
keys = re.findall(r'key=["\']([^"\']+)["\']', text)
dups = set([k for k in keys if keys.count(k) > 1])
if dups:
    print(f"DUPLICATE KEYS FOUND: {dups}")
else:
    print("ALL WIDGET KEYS ARE 100% UNIQUE!")
