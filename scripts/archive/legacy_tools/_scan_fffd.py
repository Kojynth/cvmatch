import os
hits = []
for root, _, files in os.walk('app'):
    for fn in files:
        if fn.endswith('.py'):
            p = os.path.join(root, fn)
            try:
                s = open(p, 'r', encoding='utf-8', errors='strict').read()
            except Exception:
                s = open(p, 'r', encoding='utf-8', errors='ignore').read()
            if '\ufffd' in s:
                hits.append(p)
print('U+FFFD in:', hits)

